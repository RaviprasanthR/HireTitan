"""T035: the jobs read API (contracts/rest-api.md, "Jobs")."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.repos import CompaniesRepo, DecisionsRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    queue: Queue


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    queue = Queue()
    deps = SearchJobsApiDeps(sessions=sessions, queue=queue, clock=FakeClock(NOW))
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_search_jobs_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, queue)


async def add_job(
    env: Env,
    title: str,
    *,
    company: str = "Acme",
    state: str = "explore",
    days_ago: int = 0,
    decided_by: str = "ai",
    outcome: str = "shown",
    reason: str = "Fits your roles",
    **fields: Any,
) -> UUID:
    async with env.sessions() as session:
        companies = CompaniesRepo(session)
        known = [c for c in await companies.list_all() if c.name == company]
        row = (
            known[0]
            if known
            else await companies.add(name=company, origin="user", resolution="verified")
        )
        seen = NOW - timedelta(days=days_ago)
        job = await JobsRepo(session).add(
            company_id=row.id,
            company_name=company,
            title=title,
            first_seen_at=seen,
            last_seen_at=seen,
            description=f"{title} description",
            state=state,
            **fields,
        )
        await JobsRepo(session).add_source(
            job.id, kind="company_board", url=f"https://jobs.example.com/{job.id}", seen_at=seen
        )
        await DecisionsRepo(session).record(
            job.id, outcome=outcome, decided_by=decided_by, reason=reason
        )
        await session.commit()
        return job.id


async def test_US1_AS1_explore_newest_first(env: Env) -> None:
    await add_job(env, "Older", days_ago=5)
    await add_job(env, "Newest", days_ago=0)
    await add_job(env, "Skipped", state="skipped", outcome="skipped")

    page = (await env.client.get("/api/v1/jobs", params={"list": "explore"})).json()

    assert [i["title"] for i in page["items"]] == ["Newest", "Older"]
    first = page["items"][0]
    assert first["decision"] == {
        "outcome": "shown",
        "decided_by": "ai",
        "reason": "Fits your roles",
    }
    assert first["sources"][0]["kind"] == "company_board"


async def test_FR030_filters_and_sort(env: Env) -> None:
    await add_job(env, "Zed role", company="Zeta", work_mode="remote", city="Pune", days_ago=1)
    await add_job(
        env, "Alpha role", company="Alpha", work_mode="onsite", city="Chennai", days_ago=2
    )
    get = env.client.get

    by_company = (await get("/api/v1/jobs", params={"sort": "company"})).json()["items"]
    remote = (await get("/api/v1/jobs", params={"work_mode": "remote"})).json()["items"]
    pune = (await get("/api/v1/jobs", params={"city": "pune"})).json()["items"]

    assert [i["company_name"] for i in by_company] == ["Alpha", "Zeta"]
    assert [i["title"] for i in remote] == ["Zed role"]
    assert [i["title"] for i in pune] == ["Zed role"]
    assert (await get("/api/v1/jobs", params={"list": "other"})).status_code == 422


async def test_keyset_paging_returns_every_job_once(env: Env) -> None:
    for n in range(5):
        await add_job(env, f"Job {n}", days_ago=n)
    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = (await env.client.get("/api/v1/jobs", params=params)).json()
        seen += [i["title"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"Job {n}" for n in range(5)]


async def test_US1_AS5_restore_keeps_job_in_explore_on_next_search(env: Env) -> None:
    job_id = await add_job(env, "Skipped one", state="skipped", outcome="skipped")

    restored = await env.client.post(f"/api/v1/jobs/{job_id}/restore")

    assert restored.status_code == 200
    assert (restored.json()["state"], restored.json()["restored"]) == ("explore", True)
    again = await env.client.post(f"/api/v1/jobs/{job_id}/restore")
    assert again.status_code == 409  # only a skipped job can be restored


async def test_FR032_detail_has_sources_reason_and_first_search(env: Env) -> None:
    job_id = await add_job(
        env,
        "Backend Engineer",
        injection_flags=[{"rule_id": "x", "severity": "high", "excerpt": "e", "location": "d"}],
        skills_found=["python"],
    )

    detail = (await env.client.get(f"/api/v1/jobs/{job_id}")).json()

    assert detail["description"] == "Backend Engineer description"
    assert detail["sources"][0]["url"].startswith("https://jobs.example.com/")
    assert detail["decision"]["reason"] == "Fits your roles"
    assert [d["decided_by"] for d in detail["decision_history"]] == ["ai"]
    assert detail["injection_flags"][0]["severity"] == "high"
    assert detail["skills_found"] == ["python"]
    assert detail["first_search_id"] is None  # added by hand in this test
    assert (await env.client.get(f"/api/v1/jobs/{UUID(int=3)}")).status_code == 404


async def test_FR041_delete_is_a_tombstone(env: Env) -> None:
    job_id = await add_job(env, "Gone")

    assert (await env.client.delete(f"/api/v1/jobs/{job_id}")).status_code == 204

    page = (await env.client.get("/api/v1/jobs")).json()
    assert page["items"] == []
    async with env.sessions() as session:
        row = await session.get(JobRow, job_id)
        assert row is not None
        assert row.state == "deleted"  # the row stays so a later search does not add it again
    assert (await env.client.delete(f"/api/v1/jobs/{job_id}")).status_code == 409


async def test_recheck_only_for_rules_only_fallback_jobs(env: Env) -> None:
    fallback = await add_job(
        env, "Unchecked", decided_by="rules_only_fallback", reason="not checked by AI"
    )
    judged = await add_job(env, "Judged")

    ok = await env.client.post(f"/api/v1/jobs/{fallback}/recheck")
    refused = await env.client.post(f"/api/v1/jobs/{judged}/recheck")

    assert ok.status_code == 202
    assert env.queue.enqueued == [UUID(ok.json()["run_id"])]
    assert (refused.status_code, refused.json()["reason"]) == (409, "not_recheckable")


async def test_SC010_first_page_fast_with_1000_jobs(env: Env) -> None:
    async with env.sessions() as session:
        company = await CompaniesRepo(session).add(name="Big", origin="user", resolution="verified")
        await session.execute(
            text(
                """
                INSERT INTO app.jobs (id, company_id, company_name, title, first_seen_at,
                                      last_seen_at, description, state, posted_at)
                SELECT gen_random_uuid(), :cid, 'Big', 'Job ' || n, :now, :now, 'd', 'explore',
                       :now - (n || ' minutes')::interval
                FROM generate_series(1, 1000) AS n
                """
            ),
            {"cid": company.id, "now": NOW},
        )
        await session.execute(text("ANALYZE app.jobs"))
        await session.commit()

    started = time.perf_counter()
    page = (await env.client.get("/api/v1/jobs", params={"limit": 25})).json()
    elapsed = time.perf_counter() - started

    assert len(page["items"]) == 25
    assert elapsed < 1.0
    async with env.sessions() as session:
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in await session.execute(
                text(
                    "EXPLAIN SELECT * FROM app.jobs WHERE state = 'explore' "
                    "ORDER BY sort_key DESC, id LIMIT 26"
                )
            )
        )
    assert "ix_jobs_state_sort" in plan


async def test_role_is_the_ai_role_or_the_title_cut_down_by_rules(env: Env) -> None:
    await add_job(env, "Senior Backend Engineer (Python) - Pune", days_ago=0)
    await add_job(env, "Backend Engineer - Remote - Req 9912", days_ago=1, role_short="Backend Eng")

    page = (await env.client.get("/api/v1/jobs", params={"list": "explore"})).json()

    assert [(i["title"], i["role"]) for i in page["items"]] == [
        ("Senior Backend Engineer (Python) - Pune", "Senior Backend Engineer"),
        ("Backend Engineer - Remote - Req 9912", "Backend Eng"),
    ]


async def test_US2_AS5_job_card_and_detail_carry_the_company_id(env: Env) -> None:
    job_id = await add_job(env, "Backend Engineer", company="Acme")
    async with env.sessions() as session:
        company = next(c for c in await CompaniesRepo(session).list_all() if c.name == "Acme")

    detail = (await env.client.get(f"/api/v1/jobs/{job_id}")).json()
    card = (await env.client.get("/api/v1/jobs")).json()["items"][0]

    assert detail["company_id"] == str(company.id)
    assert card["company_id"] == str(company.id)


async def test_US2_AS5_a_job_without_a_company_has_a_null_company_id(env: Env) -> None:
    async with env.sessions() as session:
        job = await JobsRepo(session).add(
            company_id=None,
            company_name="Pasted Co",
            title="Pasted Role",
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="pasted text",
            state="explore",
        )
        await DecisionsRepo(session).record(
            job.id, outcome="shown", decided_by="ai", reason="Pasted by hand"
        )
        await session.commit()
        job_id = job.id

    detail = (await env.client.get(f"/api/v1/jobs/{job_id}")).json()

    assert detail["company_id"] is None


async def test_job_card_has_inquired_on(env: Env) -> None:
    inquired = await add_job(env, "Asked About", state="inquired", inquired_on=date(2026, 11, 10))
    await add_job(env, "Browsing")

    detail = (await env.client.get(f"/api/v1/jobs/{inquired}")).json()
    card = (await env.client.get("/api/v1/jobs")).json()["items"][0]

    assert (detail["state"], detail["inquired_on"]) == ("inquired", "2026-11-10")
    assert detail["applied_on"] is None
    assert card["title"] == "Browsing"
    assert card["inquired_on"] is None
