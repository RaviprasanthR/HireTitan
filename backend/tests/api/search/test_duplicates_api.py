"""T036: possible duplicates (contracts/rest-api.md; FR-021, SC-008)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.duplicates import SearchDuplicatesApiDeps, create_duplicates_router
from hiretitan.search.infra.models import JobRow, JobSourceRow, PossibleDuplicateRow
from hiretitan.search.infra.repos import CompaniesRepo, DuplicatesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
BASE = "/api/v1/jobs/duplicates"


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchDuplicatesApiDeps(sessions=sessions, clock=FakeClock(NOW))
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_duplicates_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def add_pair(env: Env) -> tuple[UUID, UUID]:
    """Two similar jobs of one company, each with its own source; returns (keep, other)."""
    async with env.sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        ids = []
        for title, url in (
            ("Backend Engineer", "https://a.example.com/1"),
            ("Backend Engineer (Python)", "https://b.example.com/2"),
        ):
            job = await JobsRepo(session).add(
                company_id=company.id,
                company_name="Acme",
                title=title,
                first_seen_at=NOW,
                last_seen_at=NOW,
                description="d",
                state="explore",
            )
            await JobsRepo(session).add_source(job.id, kind="company_board", url=url, seen_at=NOW)
            ids.append(job.id)
        first, second = sorted(ids)
        await DuplicatesRepo(session).add(first, second, similarity=0.92)
        await session.commit()
        return first, second


async def pair_id(env: Env) -> str:
    return (await env.client.get(BASE)).json()["items"][0]["id"]


async def test_list_shows_open_pairs_side_by_side(env: Env) -> None:
    keep, other = await add_pair(env)

    page = (await env.client.get(BASE)).json()

    assert len(page["items"]) == 1
    item = page["items"][0]
    assert (item["job_a"]["id"], item["job_b"]["id"]) == (str(keep), str(other))
    assert item["similarity"] == pytest.approx(0.92)
    assert item["status"] == "open"


async def test_FR021_merge_moves_sources(env: Env) -> None:
    keep, other = await add_pair(env)

    merged = await env.client.post(f"{BASE}/{await pair_id(env)}/merge")

    assert merged.status_code == 200
    assert merged.json()["status"] == "merged"
    async with env.sessions() as session:
        sources = {
            s.url
            for s in await session.scalars(select(JobSourceRow).where(JobSourceRow.job_id == keep))
        }
        assert sources == {"https://a.example.com/1", "https://b.example.com/2"}
        loser = await session.get(JobRow, other)
        assert loser is not None
        assert loser.state == "deleted"
        winner = await session.get(JobRow, keep)
        assert winner is not None
        assert winner.state == "explore"
    assert (await env.client.get(BASE)).json()["items"] == []


async def test_FR021_dismiss_keeps_both(env: Env) -> None:
    keep, other = await add_pair(env)

    dismissed = await env.client.post(f"{BASE}/{await pair_id(env)}/dismiss")

    assert (dismissed.status_code, dismissed.json()["status"]) == (200, "dismissed")
    async with env.sessions() as session:
        states = {j.id: j.state for j in await session.scalars(select(JobRow))}
    assert states == {keep: "explore", other: "explore"}
    assert (await env.client.get(BASE)).json()["items"] == []


async def test_deciding_twice_or_an_unknown_pair_is_refused(env: Env) -> None:
    await add_pair(env)
    pair = await pair_id(env)
    assert (await env.client.post(f"{BASE}/{pair}/dismiss")).status_code == 200

    assert (await env.client.post(f"{BASE}/{pair}/merge")).status_code == 409
    assert (await env.client.post(f"{BASE}/{UUID(int=5)}/merge")).status_code == 404


async def test_SC008_no_automatic_fuzzy_merge(env: Env) -> None:
    keep, other = await add_pair(env)

    await env.client.get(BASE)  # reading the list changes nothing

    async with env.sessions() as session:
        rows = (await session.scalars(select(PossibleDuplicateRow))).all()
        jobs = (await session.scalars(select(JobRow))).all()
    assert [r.status for r in rows] == ["open"]
    assert {j.state for j in jobs} == {"explore"}
    assert {keep, other} == {j.id for j in jobs}
