"""Interview notes through the life of a job: undo, delete and merge (feature 002e, FR-011/012)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.duplicates import SearchDuplicatesApiDeps, create_duplicates_router
from hiretitan.search.api.interviews import SearchInterviewsApiDeps, create_interviews_router
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.domain.interviews import check_contact
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import (
    InterviewQuestionRow,
    InterviewRoundRow,
    PipelineDetailsRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, DuplicatesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
TODAY = date(2026, 11, 6)


class _Queue:
    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        raise AssertionError("nothing here starts a run")


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    clock = FakeClock(NOW)
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_duplicates_router(SearchDuplicatesApiDeps(sessions=sessions, clock=clock)),
            create_search_jobs_router(
                SearchJobsApiDeps(sessions=sessions, queue=_Queue(), clock=clock)
            ),
            create_interviews_router(SearchInterviewsApiDeps(sessions=sessions)),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def add_jobs(env: Env, count: int = 1) -> list[UUID]:
    """Applied jobs of one company; ids come back oldest-first (the merge keeps the first)."""
    async with env.sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        ids = []
        for n in range(count):
            job = await JobsRepo(session).add(
                company_id=company.id,
                company_name="Acme",
                title=f"Backend Engineer {n}",
                first_seen_at=NOW,
                last_seen_at=NOW,
                description="d",
                state="applied",
                applied_on=TODAY,
            )
            await JobsRepo(session).add_source(
                job.id, kind="company_board", url=f"https://a.example.com/{n}", seen_at=NOW
            )
            ids.append(job.id)
        await session.commit()
        return sorted(ids)


async def notes(
    env: Env,
    job_id: UUID,
    *,
    contact: str | None = None,
    firm: str | None = None,
    rounds: list[tuple[str, str | None]] | None = None,
) -> None:
    """Record a contact, a hiring firm and rounds; each round is (state, question or None)."""
    async with env.sessions() as session:
        repo = InterviewsRepo(session)
        if contact:
            fields, _ = check_contact(name=contact)
            assert fields is not None
            await repo.upsert_contact(job_id, fields)
        if firm:
            await repo.set_source(job_id, "hiring_firm", firm)
        for state, question in rounds or []:
            row = await repo.add_round(job_id, kind="technical")
            await repo.update_round(row.id, {"state": state})
            if question:
                await repo.add_question(row.id, question, None)
        await session.commit()


async def read(env: Env, job_id: UUID) -> dict:  # type: ignore[type-arg]
    response = await env.client.get(f"/api/v1/jobs/{job_id}/interview")
    assert response.status_code == 200, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


async def merge(env: Env, keep: UUID, other: UUID) -> None:
    async with env.sessions() as session:
        await DuplicatesRepo(session).add(keep, other, similarity=0.9)
        await session.commit()
    pair = (await env.client.get("/api/v1/jobs/duplicates")).json()["items"][0]["id"]
    response = await env.client.post(f"/api/v1/jobs/duplicates/{pair}/merge")
    assert response.status_code == 200, response.text


async def counts(env: Env) -> tuple[int, int, int]:
    async with env.sessions() as session:
        found = [
            await session.scalar(select(func.count()).select_from(table)) or 0
            for table in (PipelineDetailsRow, InterviewRoundRow, InterviewQuestionRow)
        ]
    return (found[0], found[1], found[2])


async def test_FR011_undo_keeps_details(env: Env) -> None:
    """SC-006: marking a job not applied does not touch what was recorded."""
    (job_id,) = await add_jobs(env)
    await notes(env, job_id, contact="Asha Rao", firm="TalentBridge", rounds=[("cleared", "Q1")])

    undone = await env.client.delete(f"/api/v1/jobs/{job_id}/applied")
    assert undone.status_code == 200

    body = await read(env, job_id)
    assert body["can_edit"] is False
    assert body["contact"]["name"] == "Asha Rao"
    assert body["source"] == {"kind": "hiring_firm", "firm_name": "TalentBridge"}
    assert [(r["number"], len(r["questions"])) for r in body["rounds"]] == [(1, 1)]


async def test_FR011_delete_job_removes_details(env: Env) -> None:
    (job_id,) = await add_jobs(env)
    await notes(env, job_id, contact="Asha Rao", firm="TalentBridge", rounds=[("cleared", "Q1")])
    assert await counts(env) == (1, 1, 1)

    response = await env.client.delete(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 204
    assert await counts(env) == (0, 0, 0)


async def test_FR012_merge_keeps_winner_fills_gaps(env: Env) -> None:
    keep, other = await add_jobs(env, 2)
    await notes(env, keep, contact="Winner Contact")
    await notes(env, other, contact="Loser Contact", firm="TalentBridge")

    await merge(env, keep, other)

    body = await read(env, keep)
    assert body["contact"]["name"] == "Winner Contact"  # the winner's own contact is kept
    assert body["source"] == {"kind": "hiring_firm", "firm_name": "TalentBridge"}  # a gap filled
    async with env.sessions() as session:
        left = await session.scalar(
            select(func.count())
            .select_from(PipelineDetailsRow)
            .where(PipelineDetailsRow.job_id == other)
        )
    assert left == 0


async def test_FR012_merge_moves_a_contact_when_the_winner_has_none(env: Env) -> None:
    keep, other = await add_jobs(env, 2)
    await notes(env, other, contact="Loser Contact")

    await merge(env, keep, other)

    assert (await read(env, keep))["contact"]["name"] == "Loser Contact"


async def test_FR012_merge_moves_rounds_only_when_winner_has_none(env: Env) -> None:
    keep, other = await add_jobs(env, 2)
    await notes(env, keep, rounds=[("cleared", None)])
    await notes(env, other, rounds=[("scheduled", "Lost question"), ("failed", None)])

    await merge(env, keep, other)

    body = await read(env, keep)
    assert [(r["number"], r["state"]) for r in body["rounds"]] == [(1, "cleared")]
    assert await counts(env) == (0, 1, 0)  # the loser's rounds and questions are gone


async def test_FR012_merge_moves_the_losers_rounds_renumbered_with_their_questions(
    env: Env,
) -> None:
    keep, other = await add_jobs(env, 2)
    await notes(env, other, rounds=[("cleared", "Q one"), ("cleared", None), ("scheduled", "Q3")])
    async with env.sessions() as session:  # a gap in the numbers: round 2 removed
        repo = InterviewsRepo(session)
        second = next(r for r in (await repo.details(other)).rounds if r.round.number == 2)
        await repo.delete_round(second.round.id)
        await session.commit()

    await merge(env, keep, other)

    body = await read(env, keep)
    assert [(r["number"], r["state"]) for r in body["rounds"]] == [(1, "cleared"), (2, "scheduled")]
    assert [[q["question"] for q in r["questions"]] for r in body["rounds"]] == [["Q one"], ["Q3"]]
    assert body["status"] == {"state": "scheduled", "round": 2}
