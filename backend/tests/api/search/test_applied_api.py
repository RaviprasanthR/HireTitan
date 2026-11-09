"""T043: the applied endpoints (contracts/rest-api.md, "Jobs"; FR-036, FR-037)."""

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
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
TODAY = date(2026, 11, 6)


class _Queue:
    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        raise AssertionError("applied never starts a run")


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchJobsApiDeps(sessions=sessions, queue=_Queue(), clock=FakeClock(NOW))
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_search_jobs_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def add_job(env: Env, title: str, *, state: str = "explore") -> UUID:
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
        )
        await session.commit()
        return job.id


async def test_FR036_mark_and_undo(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer")

    marked = await env.client.post(
        f"/api/v1/jobs/{job_id}/applied", json={"applied_on": "2026-11-03"}
    )

    assert marked.status_code == 200
    assert (marked.json()["state"], marked.json()["applied_on"]) == ("applied", "2026-11-03")
    assert (await env.client.get("/api/v1/jobs")).json()["items"] == []

    undone = await env.client.delete(f"/api/v1/jobs/{job_id}/applied")

    assert undone.status_code == 200
    assert (undone.json()["state"], undone.json()["applied_on"]) == ("explore", None)
    assert len((await env.client.get("/api/v1/jobs")).json()["items"]) == 1


async def test_marking_without_a_body_uses_today(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer")

    marked = await env.client.post(f"/api/v1/jobs/{job_id}/applied")

    assert marked.status_code == 200
    assert marked.json()["applied_on"] == "2026-11-06"


async def test_a_skipped_job_can_be_marked_applied(env: Env) -> None:
    job_id = await add_job(env, "Found by hand", state="skipped")

    marked = await env.client.post(f"/api/v1/jobs/{job_id}/applied", json={})

    assert marked.status_code == 200
    assert marked.json()["state"] == "applied"


@pytest.mark.parametrize("applied_on", ["2026-11-07", "2024-11-05"])
async def test_FR036_future_date_422(env: Env, applied_on: str) -> None:
    job_id = await add_job(env, "Backend Engineer")

    response = await env.client.post(
        f"/api/v1/jobs/{job_id}/applied", json={"applied_on": applied_on}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "applied_on"
    assert (await env.client.get(f"/api/v1/jobs/{job_id}")).json()["state"] == "explore"


async def test_a_deleted_job_cannot_be_marked_and_an_unknown_one_is_404(env: Env) -> None:
    deleted = await add_job(env, "Gone", state="deleted")

    assert (await env.client.post(f"/api/v1/jobs/{deleted}/applied")).status_code == 404
    assert (await env.client.post(f"/api/v1/jobs/{UUID(int=5)}/applied")).status_code == 404


async def test_undo_only_for_an_applied_job(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer")

    response = await env.client.delete(f"/api/v1/jobs/{job_id}/applied")

    assert response.status_code == 409
    assert response.json()["reason"] == "not_applied"


async def test_marking_twice_is_a_conflict(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer", state="applied")

    response = await env.client.post(f"/api/v1/jobs/{job_id}/applied")

    assert response.status_code == 409
    assert response.json()["reason"] == "already_applied"


async def test_FR037_applied_list_ordered_by_date(env: Env) -> None:
    ids = {t: await add_job(env, t) for t in ("Oldest", "Newest", "Middle")}
    for title, day in (
        ("Oldest", "2026-10-01"),
        ("Newest", "2026-11-05"),
        ("Middle", "2026-10-20"),
    ):
        await env.client.post(f"/api/v1/jobs/{ids[title]}/applied", json={"applied_on": day})

    page = (await env.client.get("/api/v1/jobs", params={"list": "applied", "limit": 2})).json()
    assert [j["title"] for j in page["items"]] == ["Newest", "Middle"]
    assert page["next_cursor"]

    rest = (
        await env.client.get(
            "/api/v1/jobs", params={"list": "applied", "limit": 2, "cursor": page["next_cursor"]}
        )
    ).json()
    assert [j["title"] for j in rest["items"]] == ["Oldest"]
    assert rest["next_cursor"] is None
