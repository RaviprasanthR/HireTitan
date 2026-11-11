"""T020: open-role counts per company, derived from the Explore list (US3, FR-017, SC-005)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.search.application.openings import jobs_for_area, openings_by_company
from hiretitan.search.infra.repos import CompaniesRepo, JobFilters, JobsRepo, OpeningsRepo

T0 = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture
async def session(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessions() as session:
        yield session


async def company(session: AsyncSession, name: str, *, searched: bool = True) -> UUID:
    row = await CompaniesRepo(session).add(name=name, origin="user", resolution="verified")
    if searched:
        await CompaniesRepo(session).set_fields(row.id, last_checked_at=T0)
    return row.id


async def job(
    session: AsyncSession,
    company_id: UUID,
    title: str,
    *,
    state: str = "explore",
    listed: bool = True,
) -> UUID:
    row = await JobsRepo(session).add(
        company_id=company_id,
        company_name="Co",
        title=title,
        description="text",
        state=state,
        listed=listed,
        first_seen_at=T0,
        last_seen_at=T0,
        applied_on=T0.date() if state == "applied" else None,
    )
    return row.id


async def test_US3_AS1_counts_per_area(session: AsyncSession) -> None:
    a = await company(session, "A")
    b = await company(session, "B")
    await job(session, a, "Senior Frontend Engineer")
    await job(session, a, "Backend Developer (Go)")
    await job(session, a, "SDET")
    await job(session, a, "Marketing Manager")
    await job(session, b, "Backend Engineer")
    await session.commit()
    result = await openings_by_company(OpeningsRepo(session))
    assert result[a] == {"frontend": 1, "backend": 1, "qa": 1}
    assert result[b] == {"frontend": 0, "backend": 1, "qa": 0}


async def test_US3_AS3_full_stack_counts_in_both(session: AsyncSession) -> None:
    a = await company(session, "A")
    await job(session, a, "Full Stack Engineer")
    await session.commit()
    assert (await openings_by_company(OpeningsRepo(session)))[a] == {
        "frontend": 1,
        "backend": 1,
        "qa": 0,
    }


async def test_US3_AS4_applied_skipped_deleted_and_unlisted_not_counted(
    session: AsyncSession,
) -> None:
    a = await company(session, "A")
    await job(session, a, "Backend Engineer", state="applied")
    await job(session, a, "Backend Engineer", state="skipped")
    await job(session, a, "Backend Engineer", state="deleted")
    await job(session, a, "Backend Engineer", listed=False)
    await session.commit()
    assert (await openings_by_company(OpeningsRepo(session)))[a] == {
        "frontend": 0,
        "backend": 0,
        "qa": 0,
    }


async def test_US3_AS5_never_searched_is_null_not_zero(session: AsyncSession) -> None:
    never = await company(session, "Never", searched=False)
    zero = await company(session, "Zero")
    await session.commit()
    result = await openings_by_company(OpeningsRepo(session))
    assert result[never] is None
    assert result[zero] == {"frontend": 0, "backend": 0, "qa": 0}


async def test_SC005_counts_equal_explore_list_for_every_company(session: AsyncSession) -> None:
    ids = [await company(session, f"C{n}") for n in range(3)]
    titles = ["Frontend Engineer", "Backend Engineer", "QA Engineer", "Full Stack Developer"]
    for n, company_id in enumerate(ids):
        for title in titles[: n + 2]:
            await job(session, company_id, title)
    await session.commit()
    counts = await openings_by_company(OpeningsRepo(session))
    for company_id in ids:
        listed = await JobsRepo(session).page(
            JobFilters(state="explore", company_id=company_id), limit=100
        )
        for area in ("frontend", "backend", "qa"):
            rows = await jobs_for_area(OpeningsRepo(session), company_id, area)  # type: ignore[arg-type]
            assert len(rows) == (counts[company_id] or {})[area]
            assert {r.id for r in rows} <= {r.id for r in listed.items}


async def test_openings_use_one_query_for_all_companies(session: AsyncSession) -> None:
    for n in range(5):
        company_id = await company(session, f"C{n}")
        await job(session, company_id, "Backend Engineer")
    await session.commit()
    statements: list[str] = []

    def record(conn: object, cursor: object, statement: str, *rest: object) -> None:
        statements.append(statement)

    target = session.get_bind()
    event.listen(target, "before_cursor_execute", record)
    try:
        await openings_by_company(OpeningsRepo(session))
    finally:
        event.remove(target, "before_cursor_execute", record)
    assert len(statements) == 1
