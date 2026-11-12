"""T057: AI status and checklist (FR-028 to FR-030, US3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.preferences.application.service import save_preferences
from hiretitan.preferences.domain.defaults import default_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import ResumeFilesRepo, VersionsRepo
from hiretitan.search.infra.repos import RuleSetsRepo, SearchRunsRepo
from hiretitan.setup.api.status import StatusApiDeps, create_status_router
from hiretitan.setup_wiring import RepoFacts


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    key_checks: list[int]


@pytest.fixture
async def env(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path, fake_clock: FakeClock
) -> AsyncIterator[Env]:
    key_checks: list[int] = []

    async def enqueue_key_check() -> None:
        key_checks.append(1)

    deps = StatusApiDeps(
        sessions=sessions,
        clock=fake_clock,
        provider="openai",
        facts=RepoFacts,
        enqueue_key_check=enqueue_key_check,
    )
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_status_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, key_checks)


async def test_US3_AS1_missing_key_reported(env: Env) -> None:
    async with env.sessions() as session:
        await ProviderStatusRepo(session).set(
            "openai", "missing", "No API key is set. Add OPENAI_API_KEY to your .env file."
        )
        await session.commit()

    data = (await env.client.get("/api/v1/status")).json()

    assert data["ai"]["provider"] == "openai"
    assert data["ai"]["status"] == "missing"
    assert "OPENAI_API_KEY" in data["ai"]["message"]
    assert data["checklist"]["key_ok"] is False


async def test_R7_status_reports_out_of_credit(env: Env) -> None:
    async with env.sessions() as session:
        await ProviderStatusRepo(session).set(
            "openai", "out_of_credit", "You exceeded your current quota."
        )
        await session.commit()

    data = (await env.client.get("/api/v1/status")).json()

    assert data["ai"]["status"] == "out_of_credit"
    assert data["ai"]["message"] == "You exceeded your current quota."
    assert data["checklist"]["key_ok"] is False


async def test_status_is_unknown_before_the_first_check(env: Env) -> None:
    data = (await env.client.get("/api/v1/status")).json()
    assert data["ai"]["status"] == "unknown"
    assert data["checklist"] == {
        "key_ok": False,
        "resume_uploaded": False,
        "profile_confirmed": False,
        "preferences_saved": False,
        "rules_approved": False,
        "searched_once": False,
    }
    assert "budget" not in data


async def test_FR028_checklist_reflects_state(env: Env, fake_clock: FakeClock) -> None:
    async with env.sessions() as session:
        await ProviderStatusRepo(session).set("openai", "working", None)
        await ResumeFilesRepo(session).create(
            kind="upload_pdf", original_name="r.pdf", size_bytes=10, sha256="a" * 64
        )
        await session.commit()
    checklist = (await env.client.get("/api/v1/status")).json()["checklist"]
    assert checklist == {
        "key_ok": True,
        "resume_uploaded": True,
        "profile_confirmed": False,
        "preferences_saved": False,
        "rules_approved": False,
        "searched_once": False,
    }

    async with env.sessions() as session:
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane"), skills=("Python",)), created_by="manual"
        )
        await save_preferences(
            PreferencesRepo(session),
            fake_clock,
            replace(default_preferences(), target_roles=("Engineer",)),
        )
        await session.commit()
    checklist = (await env.client.get("/api/v1/status")).json()["checklist"]
    assert checklist == {
        "key_ok": True,
        "resume_uploaded": True,
        "profile_confirmed": True,
        "preferences_saved": True,
        "rules_approved": False,
        "searched_once": False,
    }


async def test_US1_AS11_checklist_includes_rules_approved(env: Env) -> None:
    async with env.sessions() as session:
        repo = RuleSetsRepo(session)
        proposal = await repo.propose({}, {})
        await session.commit()
    checklist = (await env.client.get("/api/v1/status")).json()["checklist"]
    assert checklist["rules_approved"] is False  # a proposal is not approval

    async with env.sessions() as session:
        await RuleSetsRepo(session).approve(proposal.id)
        await session.commit()
    checklist = (await env.client.get("/api/v1/status")).json()["checklist"]
    assert checklist["rules_approved"] is True


async def test_searched_once_false_until_first_run(env: Env) -> None:
    assert (await env.client.get("/api/v1/status")).json()["checklist"]["searched_once"] is False

    async with env.sessions() as session:
        rules = RuleSetsRepo(session)
        rule_set = await rules.approve((await rules.propose({}, {})).id)
        workflow = await RunsRepo(session).create("job_search")
        await SearchRunsRepo(session).create(
            workflow_run_id=workflow.id,
            rule_set_id=rule_set.id,
            mode="rules_only",
            company_order=[],
        )
        await session.commit()

    assert (await env.client.get("/api/v1/status")).json()["checklist"]["searched_once"] is True


async def test_US3_AS2_check_again_enqueues_key_check(env: Env) -> None:
    res = await env.client.post("/api/v1/status/ai/check")
    assert res.status_code == 202
    assert env.key_checks == [1]


async def test_FR029_status_never_includes_key(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-123")
    res = await env.client.get("/api/v1/status")
    assert "sk-secret-value-123" not in res.text
