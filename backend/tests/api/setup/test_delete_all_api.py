"""T064: delete all my data (FR-035, US4 scenario 2, SC-008)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.preferences.application.service import save_preferences
from hiretitan.preferences.domain.defaults import default_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import Provenance, ResumeFilesRepo, ReviewsRepo, VersionsRepo
from hiretitan.setup.api.data import DataApiDeps, create_data_router
from hiretitan.setup.api.onboarding import OnboardingApiDeps, create_onboarding_router
from hiretitan.setup.infra.settings_repo import SettingsRepo
from hiretitan.setup_wiring import RepoFacts, SqlDeleteAllStore

URL = "/api/v1/data/delete-all"
# Rows that exist on a fresh install and come back after a wipe.
RESEEDED = {"settings", "provider_status"}


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    storage: LocalFileStorage
    data_dir: Path
    key_checks: list[int] = field(default_factory=list)


@pytest.fixture
async def env(
    sessions: async_sessionmaker[AsyncSession],
    profile_saver: BaseCheckpointSaver,  # type: ignore[type-arg]  # creates the lg tables
    tmp_path: Path,
    fake_clock: FakeClock,
) -> AsyncIterator[Env]:
    storage = LocalFileStorage(tmp_path / "data")
    key_checks: list[int] = []

    async def enqueue_key_check() -> None:
        key_checks.append(1)

    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_data_router(
                DataApiDeps(
                    sessions=sessions,
                    storage=storage,
                    store=SqlDeleteAllStore,
                    enqueue_key_check=enqueue_key_check,
                )
            ),
            create_onboarding_router(
                OnboardingApiDeps(sessions=sessions, clock=fake_clock, facts=RepoFacts)
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, storage, tmp_path / "data", key_checks)


async def populate(env: Env, clock: FakeClock) -> UUID:
    """Leave something in every kind of table; returns the id of a still-open run."""
    sha = env.storage.put(b"resume text for the wipe test")
    env.storage.put_text(sha, "txt", "extracted")
    async with env.sessions() as session:
        file = await ResumeFilesRepo(session).create(
            kind="pasted_text", original_name="pasted text", size_bytes=29, sha256=sha
        )
        runs = RunsRepo(session)
        done = await runs.create("profile_ingest", subject_id=file.id)
        await runs.transition(done.id, RunStatus.running)
        await runs.transition(done.id, RunStatus.done)
        queued = await runs.create("profile_ingest")
        await ReviewsRepo(session).create(
            run_id=done.id,
            resume_file_id=file.id,
            extraction={},
            dropped_items=[],
            flags={},
            provenance=Provenance("extract_profile", "1", "fake", "fake-model"),
        )
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane"), skills=("Python",)),
            created_by="extraction",
            source_file_id=file.id,
            provenance=Provenance("extract_profile", "1", "fake", "fake-model"),
        )
        await save_preferences(
            PreferencesRepo(session),
            clock,
            replace(default_preferences(), target_roles=("Engineer",)),
        )
        await CallsRepo(session).record(
            LlmCallRecord(
                "extract_profile",
                "extract_profile",
                "1",
                "fake",
                "fake-model",
                10,
                0,
                5,
                Decimal("0.01"),
                Decimal("0.01"),
                120,
                "ok",
            )
        )
        await ProviderStatusRepo(session).set("openai", "working", None)
        settings_repo = SettingsRepo(session)
        await settings_repo.write_display_name("Jane")
        await settings_repo.write_setup_completed(clock.now())
        await settings_repo.write_budget_cap(Decimal("40.00"))
        await session.execute(
            text(
                "INSERT INTO lg.checkpoints (thread_id, checkpoint_ns, checkpoint_id, checkpoint,"
                " metadata) VALUES ('t', '', 'c1', '{}', '{}')"
            )
        )
        await session.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, args)"
                " VALUES ('default', 'run_workflow', '{}')"
            )
        )
        await session.commit()
    return queued.id


async def table_counts(env: Env) -> dict[str, int]:
    async with env.sessions() as session:
        names = (
            await session.execute(
                text(
                    "SELECT table_schema || '.' || table_name FROM information_schema.tables"
                    " WHERE table_type = 'BASE TABLE' AND ("
                    "  (table_schema = 'app' AND table_name <> 'alembic_version')"
                    "  OR (table_schema = 'lg' AND table_name <> 'checkpoint_migrations')"
                    "  OR (table_schema = 'public' AND table_name LIKE 'procrastinate_jobs'))"
                )
            )
        ).scalars()
        counts = {}
        for name in names.all():
            counts[name] = (
                await session.execute(text(f"SELECT count(*) FROM {name}"))
            ).scalar_one()
    return counts


def stored_files(env: Env) -> list[Path]:
    root = env.data_dir / "files"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


async def test_US4_AS2_returns_to_first_run_state(env: Env, fake_clock: FakeClock) -> None:
    await populate(env, fake_clock)

    response = await env.client.post(URL, json={"confirm": "DELETE"})

    assert response.status_code == 204
    async with env.sessions() as session:
        record = await SettingsRepo(session).read_onboarding()
        status = await ProviderStatusRepo(session).get("openai")
        cap = await SettingsRepo(session).read_budget_cap()
    assert (record.display_name, record.setup_completed_at) == (None, None)
    assert status is not None
    assert status.status == "unknown"
    assert cap == Decimal("25.00")
    assert env.key_checks == [1]


async def test_SC008_no_rows_or_files_left(env: Env, fake_clock: FakeClock) -> None:
    await populate(env, fake_clock)
    before = await table_counts(env)
    assert stored_files(env)
    assert sum(n for t, n in before.items() if t.split(".")[1] not in RESEEDED) > 0

    assert (await env.client.post(URL, json={"confirm": "DELETE"})).status_code == 204

    after = await table_counts(env)
    leftovers = {t: n for t, n in after.items() if n and t.split(".")[1] not in RESEEDED}
    assert leftovers == {}
    assert {t: n for t, n in after.items() if t.split(".")[1] in RESEEDED} == {
        "app.settings": 1,
        "app.provider_status": 1,
    }
    assert stored_files(env) == []


@pytest.mark.parametrize("body", [{"confirm": "delete"}, {"confirm": ""}, {}, {"confirm": "YES"}])
async def test_FR035_wrong_confirm_word_rejected(
    env: Env, fake_clock: FakeClock, body: dict[str, str]
) -> None:
    await populate(env, fake_clock)
    before = await table_counts(env)

    response = await env.client.post(URL, json=body)

    assert response.status_code == 422
    assert await table_counts(env) == before
    assert stored_files(env)
    assert env.key_checks == []


async def test_FR035_back_to_setup_step_1(env: Env, fake_clock: FakeClock) -> None:
    await populate(env, fake_clock)
    assert (await env.client.get("/api/v1/onboarding")).json()["step"] != 1

    assert (await env.client.post(URL, json={"confirm": "DELETE"})).status_code == 204

    view = (await env.client.get("/api/v1/onboarding")).json()
    assert view["step"] == 1
    assert view["display_name"] is None
    assert view["open_review_id"] is None
    assert view["active_run_id"] is None


async def test_open_runs_are_cancelled_before_the_wipe(env: Env, fake_clock: FakeClock) -> None:
    run_id = await populate(env, fake_clock)

    assert (await env.client.post(URL, json={"confirm": "DELETE"})).status_code == 204

    async with env.sessions() as session:
        assert await RunsRepo(session).get(run_id) is None
