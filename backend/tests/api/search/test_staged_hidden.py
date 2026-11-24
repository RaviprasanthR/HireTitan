"""002m quick flow: a pasted post held in a chat (state ``staged``) is shown nowhere.

It is not in Explore, the pipeline, the counts, the company list or the duplicate offers, and a
rule re-check, search or mail run never touches it. Only the person's yes makes it a job.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.jobs import SearchJobsArgs, search_jobs
from hiretitan.actions.spec import ActionContext
from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.api.pipeline import PipelineApiDeps, create_pipeline_router
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo
from hiretitan.search_wiring import SqlResumeLookup

NOW = datetime(2026, 11, 24, 9, tzinfo=UTC)


class Queue:
    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        return None


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    deps = SearchJobsApiDeps(
        sessions=sessions, queue=Queue(), clock=FakeClock(NOW), resume_lookup=SqlResumeLookup
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_search_jobs_router(deps),
            create_pipeline_router(PipelineApiDeps(sessions=sessions)),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


async def _add(sessions: async_sessionmaker[AsyncSession], title: str, state: str) -> UUID:
    async with sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Initech", origin="user", resolution="verified"
        )
        row = await JobsRepo(session).add(
            company_id=company.id,
            company_name="Initech",
            title=title,
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="A post held in a chat.",
            state=state,
        )
        await session.commit()
        return row.id


async def test_a_staged_job_is_in_no_list_or_count(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await _add(sessions, "Held Post", "staged")
    shown = await _add(sessions, "Shown Job", "explore")

    explore = (await client.get("/api/v1/jobs", params={"list": "explore"})).json()
    pipeline = (await client.get("/api/v1/jobs", params={"list": "pipeline"})).json()
    summary = (await client.get("/api/v1/pipeline/summary")).json()

    assert [j["id"] for j in explore["items"]] == [str(shown)]
    assert pipeline["items"] == []
    assert summary["total"] == 0


async def test_the_assistant_search_never_returns_a_staged_job(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _add(sessions, "Held Post", "staged")

    async with sessions() as session:
        ctx = ActionContext(session=session, now=NOW)
        for listing in ("explore", "pipeline", "hidden"):
            found = await search_jobs(ctx, SearchJobsArgs(list=listing))  # type: ignore[arg-type]
            assert found.total == 0, listing
            assert "Held Post" not in str(found.items)
