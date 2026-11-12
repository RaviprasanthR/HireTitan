"""The pipeline list: applied and inquired jobs together, newest first (feature 002d, US1)."""

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


async def add_job(env: Env, title: str, *, state: str = "explore", on: date = TODAY) -> UUID:
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
            applied_on=on if state == "applied" else None,
            inquired_on=on if state == "inquired" else None,
        )
        await session.commit()
        return job.id


async def _pipeline(env: Env, **params: object) -> dict:  # type: ignore[type-arg]
    return (await env.client.get("/api/v1/jobs", params={"list": "pipeline", **params})).json()  # type: ignore[no-any-return]


async def test_US1_AS2_pipeline_lists_applied_and_inquired_newest_first(env: Env) -> None:
    await add_job(env, "Old applied", state="applied", on=date(2026, 10, 1))
    await add_job(env, "New inquired", state="inquired", on=date(2026, 11, 5))
    await add_job(env, "Mid applied", state="applied", on=date(2026, 10, 20))
    await add_job(env, "Still new")  # explore: not in the pipeline

    page = await _pipeline(env)

    assert [j["title"] for j in page["items"]] == ["New inquired", "Mid applied", "Old applied"]
    assert [j["state"] for j in page["items"]] == ["inquired", "applied", "applied"]
    assert page["items"][0]["inquired_on"] == "2026-11-05"


async def test_pipeline_pages_with_a_cursor(env: Env) -> None:
    await add_job(env, "A", state="applied", on=date(2026, 10, 1))
    await add_job(env, "B", state="inquired", on=date(2026, 11, 5))
    await add_job(env, "C", state="applied", on=date(2026, 10, 20))

    first = await _pipeline(env, limit=2)
    rest = await _pipeline(env, limit=2, cursor=first["next_cursor"])

    assert [j["title"] for j in first["items"]] == ["B", "C"]
    assert first["next_cursor"]
    assert [j["title"] for j in rest["items"]] == ["A"]
    assert rest["next_cursor"] is None


async def test_the_applied_list_is_gone(env: Env) -> None:
    response = await env.client.get("/api/v1/jobs", params={"list": "applied"})

    assert response.status_code == 422


async def _state(env: Env, job_id: UUID) -> dict:  # type: ignore[type-arg]
    return (await env.client.get(f"/api/v1/jobs/{job_id}")).json()  # type: ignore[no-any-return]


async def test_US2_AS1_mark_inquired_defaults_to_today(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer")

    marked = await env.client.post(f"/api/v1/jobs/{job_id}/inquired")

    assert marked.status_code == 200
    body = marked.json()
    assert (body["state"], body["inquired_on"], body["applied_on"]) == (
        "inquired",
        "2026-11-06",
        None,
    )
    assert len((await _pipeline(env))["items"]) == 1


async def test_US2_AS5_inquired_date_rules(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer")
    url = f"/api/v1/jobs/{job_id}/inquired"

    future = await env.client.post(url, json={"inquired_on": "2026-11-07"})
    old = await env.client.post(url, json={"inquired_on": "2024-11-05"})
    edge = await env.client.post(url, json={"inquired_on": "2024-11-06"})

    for response in (future, old):
        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "inquired_on"
    assert edge.status_code == 200  # exactly two years ago is still allowed


async def test_US2_AS3_undo_inquired(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer")
    await env.client.post(f"/api/v1/jobs/{job_id}/inquired")

    undone = await env.client.delete(f"/api/v1/jobs/{job_id}/inquired")

    assert undone.status_code == 200
    assert (undone.json()["state"], undone.json()["inquired_on"]) == ("explore", None)
    assert (await _pipeline(env))["items"] == []


async def test_undo_inquired_needs_an_inquired_job(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer")

    response = await env.client.delete(f"/api/v1/jobs/{job_id}/inquired")

    assert response.status_code == 409
    assert response.json()["reason"] == "not_inquired"


async def test_marking_inquired_twice_is_a_conflict(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer", state="inquired")

    response = await env.client.post(f"/api/v1/jobs/{job_id}/inquired")

    assert response.status_code == 409
    assert response.json()["reason"] == "already_inquired"


async def test_FR007_applied_job_cannot_be_inquired_409(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer", state="applied")

    response = await env.client.post(f"/api/v1/jobs/{job_id}/inquired")

    assert response.status_code == 409
    assert response.json()["reason"] == "already_applied"


async def test_US2_AS2_inquired_then_applied(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer", state="inquired", on=date(2026, 11, 1))

    marked = await env.client.post(
        f"/api/v1/jobs/{job_id}/applied", json={"applied_on": "2026-11-05"}
    )

    body = marked.json()
    assert marked.status_code == 200
    assert (body["state"], body["applied_on"], body["inquired_on"]) == (
        "applied",
        "2026-11-05",
        None,
    )


async def test_skipped_job_can_be_inquired(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer", state="skipped")

    response = await env.client.post(f"/api/v1/jobs/{job_id}/inquired")

    assert response.status_code == 200
    assert response.json()["state"] == "inquired"


async def test_undo_applied_after_inquired_returns_to_explore(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer", state="inquired", on=date(2026, 11, 1))
    await env.client.post(f"/api/v1/jobs/{job_id}/applied")

    undone = await env.client.delete(f"/api/v1/jobs/{job_id}/applied")

    body = undone.json()  # the inquiry is not restored
    assert (body["state"], body["applied_on"], body["inquired_on"]) == ("explore", None, None)


@pytest.mark.parametrize("state", ["inquired", "applied"])
async def test_a_job_in_the_pipeline_can_be_deleted(env: Env, state: str) -> None:
    job_id = await add_job(env, "Backend Engineer", state=state)

    response = await env.client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 204
    assert (await _pipeline(env))["items"] == []
