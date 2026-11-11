"""T021: the ``area`` filter on ``GET /jobs`` (US3, FR-020)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)


class Queue:
    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        return None


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
    ) as http:
        yield http


@pytest.fixture
async def company_id(sessions: async_sessionmaker[AsyncSession]) -> UUID:
    async with sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        for title in ("Backend Engineer", "Full Stack Developer", "QA Engineer", "Designer"):
            await JobsRepo(session).add(
                company_id=company.id,
                company_name="Acme",
                title=title,
                description="text",
                state="explore",
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        await session.commit()
        return company.id


async def test_US3_AS1_counts_per_area_link_to_jobs(
    client: httpx.AsyncClient, company_id: UUID
) -> None:
    for area, expected in (("backend", 2), ("frontend", 1), ("qa", 1)):
        response = await client.get(
            "/api/v1/jobs", params={"company_id": str(company_id), "area": area}
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == expected


async def test_FR020_area_requires_company_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/jobs", params={"area": "backend"})
    assert response.status_code == 422


async def test_area_filter_returns_whole_set_without_cursor(
    client: httpx.AsyncClient, company_id: UUID
) -> None:
    response = await client.get(
        "/api/v1/jobs", params={"company_id": str(company_id), "area": "backend", "limit": 1}
    )
    body = response.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is None


async def test_unknown_area_is_422(client: httpx.AsyncClient, company_id: UUID) -> None:
    response = await client.get(
        "/api/v1/jobs", params={"company_id": str(company_id), "area": "devops"}
    )
    assert response.status_code == 422
