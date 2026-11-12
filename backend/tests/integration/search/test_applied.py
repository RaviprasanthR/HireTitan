"""T042: marking a job applied and undoing it (US5, FR-036, FR-037)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.search_env import Env, add_company, go, make_env, new_search, posting

from hiretitan.search.application.pipeline import (
    JobNotFoundError,
    PipelineDateError,
    mark_applied,
    undo_applied,
)
from hiretitan.search.application.ports import ScanOk
from hiretitan.search.domain.job_state import IllegalJobTransitionError
from hiretitan.search.infra.models import JobRow, RelevanceDecisionRow
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
TODAY = date(2026, 11, 6)


@pytest.fixture
def env(sessions: async_sessionmaker[AsyncSession]) -> Env:
    return make_env(sessions)


async def add_job(session: AsyncSession, *, state: str = "explore") -> UUID:
    company = await CompaniesRepo(session).add(name="Acme", origin="user", resolution="verified")
    job = await JobsRepo(session).add(
        company_id=company.id,
        company_name="Acme",
        title="Backend Engineer",
        first_seen_at=NOW,
        last_seen_at=NOW,
        description="d",
        state=state,
    )
    await session.commit()
    return job.id


async def test_US5_AS1_marking_moves_job_with_date(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        job_id = await add_job(session)
        row = await mark_applied(
            JobsRepo(session), job_id, applied_on=date(2026, 11, 3), today=TODAY
        )
        await session.commit()
    assert (row.state.value, row.applied_on) == ("applied", date(2026, 11, 3))


async def test_marking_without_a_date_uses_today(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        job_id = await add_job(session)
        row = await mark_applied(JobsRepo(session), job_id, today=TODAY)
    assert row.applied_on == TODAY


async def test_a_skipped_job_can_be_marked_applied(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        job_id = await add_job(session, state="skipped")
        row = await mark_applied(JobsRepo(session), job_id, today=TODAY)
    assert row.state.value == "applied"


async def test_US5_AS3_undo_returns_to_explore(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        job_id = await add_job(session)
        await mark_applied(JobsRepo(session), job_id, today=TODAY)
        row = await undo_applied(JobsRepo(session), job_id)
        await session.commit()
    assert (row.state.value, row.applied_on) == ("explore", None)


@pytest.mark.parametrize(
    ("applied_on", "ok"),
    [
        (date(2026, 11, 6), True),
        (date(2024, 11, 6), True),  # exactly two years ago
        (date(2024, 11, 5), False),
        (date(2026, 11, 7), False),
    ],
)
async def test_applied_date_bounds(
    sessions: async_sessionmaker[AsyncSession], applied_on: date, ok: bool
) -> None:
    async with sessions() as session:
        job_id = await add_job(session)
        if ok:
            row = await mark_applied(JobsRepo(session), job_id, applied_on=applied_on, today=TODAY)
            assert row.state.value == "applied"
        else:
            with pytest.raises(PipelineDateError):
                await mark_applied(JobsRepo(session), job_id, applied_on=applied_on, today=TODAY)


async def test_cannot_mark_a_deleted_or_unknown_job(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        deleted = await add_job(session, state="deleted")
        with pytest.raises(IllegalJobTransitionError):
            await mark_applied(JobsRepo(session), deleted, today=TODAY)
        with pytest.raises(JobNotFoundError):
            await mark_applied(JobsRepo(session), UUID(int=1), today=TODAY)


async def test_undo_needs_an_applied_job(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        job_id = await add_job(session)
        with pytest.raises(IllegalJobTransitionError):
            await undo_applied(JobsRepo(session), job_id)


async def test_US5_AS2_later_search_does_not_judge_skip_or_duplicate(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env))
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow))).one()
        await mark_applied(JobsRepo(session), job.id, today=TODAY)
        await session.commit()
        before = await session.scalar(select(func.count()).select_from(RelevanceDecisionRow))

    await go(env, await new_search(env, mode="rules_and_ai"))

    async with env.sessions() as session:
        jobs = list(await session.scalars(select(JobRow)))
        after = await session.scalar(select(func.count()).select_from(RelevanceDecisionRow))
    assert [(j.state, j.applied_on) for j in jobs] == [("applied", TODAY)]
    assert after == before
    assert env.llm.calls == []
