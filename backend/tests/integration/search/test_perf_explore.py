"""T059: the first screen of jobs is fast with 1,000 stored jobs (SC-010)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.infra.repos import CompaniesRepo, DecisionsRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
JOBS = 1000
LIMIT_SECONDS = 2.0


class Queue:
    async def enqueue(self, run_id: Any, resume: Any = None) -> None:
        raise AssertionError("a read must not start a run")


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    deps = SearchJobsApiDeps(sessions=sessions, queue=Queue(), clock=FakeClock(NOW))
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_search_jobs_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def fill(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        companies = [
            await CompaniesRepo(session).add(
                name=f"Company {n}", origin="user", resolution="verified"
            )
            for n in range(50)
        ]
        jobs = JobsRepo(session)
        decisions = DecisionsRepo(session)
        for n in range(JOBS):
            company = companies[n % len(companies)]
            seen = NOW - timedelta(minutes=n)
            job = await jobs.add(
                company_id=company.id,
                company_name=company.name,
                title=f"Backend Engineer {n}",
                first_seen_at=seen,
                last_seen_at=seen,
                description="Build services with Python. " * 40,
                state="explore",
                city="Pune",
                work_mode="remote",
            )
            await jobs.add_source(
                job.id, kind="company_board", url=f"https://jobs.example.com/{n}", seen_at=seen
            )
            await decisions.record(
                job.id, outcome="shown", decided_by="ai", reason="Fits your roles"
            )
        await session.commit()


async def test_SC010_first_page_under_2s_with_1000_jobs(
    sessions: async_sessionmaker[AsyncSession], client: httpx.AsyncClient
) -> None:
    await fill(sessions)

    started = time.perf_counter()
    response = await client.get("/api/v1/jobs?list=explore")
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    page = response.json()
    assert len(page["items"]) > 0
    assert page["next_cursor"] is not None  # there is more than one screen
    assert elapsed < LIMIT_SECONDS
