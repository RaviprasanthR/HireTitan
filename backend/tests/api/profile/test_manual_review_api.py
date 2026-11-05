"""T073: POST /profile/reviews/manual (contracts/rest-api.md)."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workflow" / "profile"))
from harness import Harness

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.profile.api.resumes import ProfileApiDeps
from hiretitan.profile.api.reviews import create_reviews_router

URL = "/api/v1/profile/reviews/manual"


@dataclass
class FakeQueue:
    jobs: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.jobs.append(run_id)


@dataclass
class Env:
    client: httpx.AsyncClient
    h: Harness
    queue: FakeQueue


@pytest.fixture
async def env(
    make_harness: Any, sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[Env]:
    h = make_harness([])
    queue = FakeQueue()
    deps = ProfileApiDeps(sessions=sessions, storage=h.storage, queue=queue)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_reviews_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, h, queue)


async def test_manual_review_is_accepted_and_queued(env: Env) -> None:
    res = await env.client.post(URL)
    assert res.status_code == 202
    run_id = UUID(res.json()["run_id"])
    assert env.queue.jobs == [run_id]
    assert (await env.h.run(run_id)).waiting_for is not None
    assert await env.h.review() is not None


async def test_manual_review_conflicts_with_an_open_review(env: Env) -> None:
    first = UUID((await env.client.post(URL)).json()["run_id"])
    await env.h.run(first)
    review = await env.h.review()
    assert review is not None

    res = await env.client.post(URL)

    assert res.status_code == 409
    assert res.json()["open_review_id"] == str(review.id)


async def test_FR041_cancel_active_run_then_open_manual_review(env: Env) -> None:
    uploaded = await env.h.start("synthetic-mid-2page.pdf")

    blocked = await env.client.post(URL)
    assert blocked.status_code == 409
    assert blocked.json()["active_run_id"] == str(uploaded)

    res = await env.client.post(f"{URL}?cancel_active_run=true")

    assert res.status_code == 202
    assert (await env.h.state(uploaded)).status is RunStatus.cancelled


async def test_a_running_import_gives_a_conflict_even_with_cancel(
    env: Env, sessions: async_sessionmaker[AsyncSession]
) -> None:
    from hiretitan.platform.runtime.infra.runs_repo import RunsRepo

    uploaded = await env.h.start("synthetic-mid-2page.pdf")
    async with sessions() as session:
        await RunsRepo(session).transition(uploaded, RunStatus.running)
        await session.commit()

    res = await env.client.post(f"{URL}?cancel_active_run=true")

    assert res.status_code == 409
    assert "being read" in res.json()["detail"]
