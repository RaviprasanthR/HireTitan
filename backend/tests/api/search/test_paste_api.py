"""T046: `POST /jobs/paste` (contracts/rest-api.md, "Jobs"; US4, FR-033)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
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

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)
DESCRIPTION = "We build payment APIs in Python. You will own services end to end."


class _Queue:
    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        raise AssertionError("paste never starts a run")


@dataclass
class Env:
    client: httpx.AsyncClient


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchJobsApiDeps(sessions=sessions, queue=_Queue(), clock=FakeClock(NOW))
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_search_jobs_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client)


def body(**changes: str) -> dict[str, str]:
    return {
        "url": "https://jobs.example.com/acme/1",
        "description": DESCRIPTION,
        "title": "Backend Engineer",
        "company": "Acme",
    } | changes


async def test_US4_AS1_201(env: Env) -> None:
    response = await env.client.post("/api/v1/jobs/paste", json=body())

    assert response.status_code == 201
    job = response.json()
    assert (job["title"], job["company_name"], job["state"]) == (
        "Backend Engineer",
        "Acme",
        "explore",
    )
    assert job["decision"]["reason"] == "added by you"
    assert job["merged_into"] is None
    assert [s["kind"] for s in job["sources"]] == ["paste"]
    listed = (await env.client.get("/api/v1/jobs")).json()["items"]
    assert [j["id"] for j in listed] == [job["id"]]


async def test_US4_AS2_200_merged_into(env: Env) -> None:
    first = (await env.client.post("/api/v1/jobs/paste", json=body())).json()

    again = await env.client.post(
        "/api/v1/jobs/paste", json=body(url="https://jobs.example.com/acme/1?utm_source=x")
    )

    assert again.status_code == 200
    assert again.json()["merged_into"] == first["id"]
    assert again.json()["id"] == first["id"]
    assert len((await env.client.get("/api/v1/jobs")).json()["items"]) == 1


@pytest.mark.parametrize(
    ("changes", "fields"),
    [
        ({"url": ""}, ["url"]),
        ({"description": ""}, ["description"]),
        ({"url": "", "description": ""}, ["url", "description"]),
        ({"description": "short"}, ["description"]),
        ({"url": "ftp://x.example.com/1"}, ["url"]),
    ],
)
async def test_US4_AS4_422_field_errors(
    env: Env, changes: dict[str, str], fields: list[str]
) -> None:
    response = await env.client.post("/api/v1/jobs/paste", json=body(**changes))

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert [e["field"] for e in errors] == fields
    assert all(e["message"] for e in errors)
    assert (await env.client.get("/api/v1/jobs")).json()["items"] == []


async def test_a_missing_field_is_a_field_error_too(env: Env) -> None:
    response = await env.client.post("/api/v1/jobs/paste", json={"description": DESCRIPTION})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["url"]


async def test_a_deleted_job_link_is_refused(env: Env) -> None:
    first = (await env.client.post("/api/v1/jobs/paste", json=body())).json()
    assert (await env.client.delete(f"/api/v1/jobs/{first['id']}")).status_code == 204

    response = await env.client.post("/api/v1/jobs/paste", json=body())

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "url"
