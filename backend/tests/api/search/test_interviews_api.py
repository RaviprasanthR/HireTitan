"""Interview tracking endpoints (feature 002e, contracts/rest-api.md)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.interviews import SearchInterviewsApiDeps, create_interviews_router
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
TODAY = date(2026, 11, 6)


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchInterviewsApiDeps(sessions=sessions)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_interviews_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def add_job(env: Env, title: str = "Backend Engineer", *, state: str = "applied") -> UUID:
    async with env.sessions() as session:
        companies = CompaniesRepo(session)
        known = [c for c in await companies.list_all() if c.name == "Acme"]
        company = (
            known[0]
            if known
            else await companies.add(name="Acme", origin="user", resolution="verified")
        )
        job = await JobsRepo(session).add(
            company_id=company.id,
            company_name="Acme",
            title=title,
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="d",
            state=state,
            applied_on=TODAY if state == "applied" else None,
            inquired_on=TODAY if state == "inquired" else None,
        )
        await session.commit()
        return job.id


async def test_read_empty_details(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.get(f"/api/v1/jobs/{job_id}/interview")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": str(job_id),
        "can_edit": True,
        "can_add_round": True,
        "contact": None,
        "source": None,
        "rounds": [],
        "status": {"state": "applied", "round": None},
    }


async def test_read_unknown_job_404(env: Env) -> None:
    response = await env.client.get("/api/v1/jobs/00000000-0000-7000-8000-000000000999/interview")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("state", "editable"),
    [("applied", True), ("inquired", True), ("explore", False), ("skipped", False)],
)
async def test_can_edit_false_outside_the_pipeline(env: Env, state: str, editable: bool) -> None:
    job_id = await add_job(env, state=state)

    body = (await env.client.get(f"/api/v1/jobs/{job_id}/interview")).json()

    assert body["can_edit"] is editable
    assert body["can_add_round"] is editable
    assert body["status"] == {"state": state, "round": None}
