"""T072: the first-run setup endpoints (FR-037 to FR-040, US5)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.preferences.application.service import save_preferences
from hiretitan.preferences.domain.defaults import default_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import Provenance, ResumeFilesRepo, ReviewsRepo, VersionsRepo
from hiretitan.setup.api.onboarding import OnboardingApiDeps, create_onboarding_router
from hiretitan.setup_wiring import RepoFacts

URL = "/api/v1/onboarding"


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path, fake_clock: FakeClock
) -> AsyncIterator[httpx.AsyncClient]:
    deps = OnboardingApiDeps(sessions=sessions, clock=fake_clock, facts=RepoFacts)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_onboarding_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def named(client: httpx.AsyncClient, name: str = "Jane") -> None:
    assert (await client.put(f"{URL}/name", json={"display_name": name})).status_code == 200


async def confirmed_profile(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane"), skills=("Python",)), created_by="manual"
        )
        await session.commit()


async def saved_preferences(sessions: async_sessionmaker[AsyncSession], clock: FakeClock) -> None:
    async with sessions() as session:
        await save_preferences(
            PreferencesRepo(session),
            clock,
            replace(default_preferences(), target_roles=("Engineer",)),
        )
        await session.commit()


async def run_in_state(
    sessions: async_sessionmaker[AsyncSession], target: RunStatus, **kw: Any
) -> Any:
    async with sessions() as session:
        repo = RunsRepo(session)
        run = await repo.create("profile_ingest")
        await repo.transition(run.id, RunStatus.running)
        if target is not RunStatus.running:
            await repo.transition(run.id, target, **kw)
        await session.commit()
    return run


async def test_US5_AS1_fresh_install_is_step_1(client: httpx.AsyncClient) -> None:
    data = (await client.get(URL)).json()
    assert data == {
        "step": 1,
        "display_name": None,
        "open_review_id": None,
        "active_run_id": None,
    }


async def test_US5_AS2_name_saved_moves_to_step_2(client: httpx.AsyncClient) -> None:
    res = await client.put(f"{URL}/name", json={"display_name": "  Jane   Example "})
    assert res.json() == {"display_name": "Jane Example"}
    data = (await client.get(URL)).json()
    assert (data["step"], data["display_name"]) == (2, "Jane Example")


@pytest.mark.parametrize("bad", ["", "   ", "x" * 121])
async def test_FR039_name_validated(client: httpx.AsyncClient, bad: str) -> None:
    res = await client.put(f"{URL}/name", json={"display_name": bad})
    assert res.status_code == 422
    assert res.json()["errors"][0]["field"] == "display_name"
    assert (await client.get(URL)).json()["step"] == 1


async def test_US5_AS3_running_resume_keeps_step_2(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await named(client)
    run = await run_in_state(sessions, RunStatus.paused, pause_reason=PauseReason.key_missing)
    data = (await client.get(URL)).json()
    assert (data["step"], data["active_run_id"]) == (2, str(run.id))


async def test_US5_AS3_injection_decision_keeps_step_2(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await named(client)
    await run_in_state(
        sessions, RunStatus.awaiting_review, waiting_for=WaitingFor.injection_decision
    )
    assert (await client.get(URL)).json()["step"] == 2


async def test_US5_AS3_open_review_is_step_3(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await named(client)
    async with sessions() as session:
        file = await ResumeFilesRepo(session).create(
            kind="upload_pdf", original_name="r.pdf", size_bytes=10, sha256="a" * 64
        )
        run = await RunsRepo(session).create("profile_ingest", subject_id=file.id)
        review = await ReviewsRepo(session).create(
            run_id=run.id,
            resume_file_id=file.id,
            extraction={},
            dropped_items=[],
            flags={},
            provenance=Provenance("extract_profile", "1", "fake", "fake-model"),
        )
        await RunsRepo(session).transition(run.id, RunStatus.running)
        await RunsRepo(session).transition(
            run.id, RunStatus.awaiting_review, waiting_for=WaitingFor.profile_review
        )
        await session.commit()
    data = (await client.get(URL)).json()
    assert (data["step"], data["open_review_id"]) == (3, str(review.id))


async def test_US5_AS3_confirmed_profile_is_step_4(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await named(client)
    await confirmed_profile(sessions)
    assert (await client.get(URL)).json()["step"] == 4


async def test_US5_AS7_complete_requires_profile_and_preferences(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    fake_clock: FakeClock,
) -> None:
    await named(client)
    assert (await client.post(f"{URL}/complete")).status_code == 409
    await confirmed_profile(sessions)
    assert (await client.post(f"{URL}/complete")).status_code == 409
    await saved_preferences(sessions, fake_clock)

    res = await client.post(f"{URL}/complete")

    assert res.status_code == 200
    assert res.json()["setup_completed_at"].startswith("2026-11-04T09:00:00")
    assert (await client.get(URL)).json()["step"] == "done"


async def test_US5_AS7_upload_after_completion_stays_done(
    client: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    fake_clock: FakeClock,
) -> None:
    await named(client)
    await confirmed_profile(sessions)
    await saved_preferences(sessions, fake_clock)
    await client.post(f"{URL}/complete")

    await run_in_state(sessions, RunStatus.running)  # a later resume upload

    assert (await client.get(URL)).json()["step"] == "done"
