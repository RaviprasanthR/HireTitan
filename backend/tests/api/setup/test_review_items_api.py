"""T058: the review list (FR-033, US3-AS6)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.infra.repos import Provenance, ResumeFilesRepo, ReviewsRepo
from hiretitan.setup.api.review_items import ReviewItemsApiDeps, create_review_items_router
from hiretitan.setup_wiring import RepoFacts


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    deps = ReviewItemsApiDeps(sessions=sessions, facts=RepoFacts)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_review_items_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_nothing_waiting_is_an_empty_list(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/review-items")).json() == []


async def test_US3_AS6_open_review_listed(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
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
            provenance=Provenance("extract_profile", "1", "openai", "gpt-5.4-mini"),
        )
        await RunsRepo(session).transition(run.id, RunStatus.running)
        await RunsRepo(session).transition(
            run.id, RunStatus.awaiting_review, waiting_for=WaitingFor.profile_review
        )
        await session.commit()

    items = (await client.get("/api/v1/review-items")).json()

    assert len(items) == 1
    assert items[0]["kind"] == "profile_review"
    assert items[0]["target"] == f"/profile/review/{review.id}"
    assert items[0]["id"] == str(run.id)


async def test_FR033_paused_and_decision_runs_listed(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        repo = RunsRepo(session)
        decision = await repo.create("profile_ingest")
        paused = await repo.create("profile_ingest")
        done = await repo.create("profile_ingest")
        for run in (decision, paused, done):
            await repo.transition(run.id, RunStatus.running)
        await repo.transition(
            decision.id, RunStatus.awaiting_review, waiting_for=WaitingFor.injection_decision
        )
        await session.commit()  # a later transaction, so "paused" is the newer item
        await repo.transition(paused.id, RunStatus.paused, pause_reason=PauseReason.budget_reached)
        await repo.transition(done.id, RunStatus.done)
        await session.commit()

    items = (await client.get("/api/v1/review-items")).json()

    by_kind = {item["kind"]: item for item in items}
    assert set(by_kind) == {"injection_decision", "paused"}
    assert by_kind["paused"]["title"] == "Paused: monthly AI budget reached"
    assert by_kind["paused"]["target"] == "/settings"
    assert by_kind["injection_decision"]["target"] == "/profile"
    assert [i["kind"] for i in items] == ["paused", "injection_decision"]  # newest first
