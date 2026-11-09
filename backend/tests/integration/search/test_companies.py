"""T048: the company list and what the person can do with it (US3, FR-016 to FR-019)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.search.application.companies import (
    CompanyError,
    CompanyNotFoundError,
    check_manually_list,
    delete_company,
    hide_company,
    list_companies,
    update_company,
)
from hiretitan.search.infra.models import CompanyRow, JobRow
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)


@pytest.fixture
async def session(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessions() as session:
        yield session


async def add(session: AsyncSession, name: str, **fields: object) -> UUID:
    values: dict[str, object] = {"origin": "user", "resolution": "verified"} | fields
    row = await CompaniesRepo(session).add(name=name, **values)
    await session.commit()
    return row.id


async def test_US3_AS1_lists_built_in_with_board_status(session: AsyncSession) -> None:
    await add(
        session, "Acme", origin="built_in", key="acme", ats_vendor="greenhouse", board_id="acme"
    )
    await add(
        session,
        "Pages Ltd",
        resolution="careers_page",
        careers_url="https://pages.example.com/jobs",
    )
    await add(session, "Keka Co", origin="built_in", key="keka-co", resolution="check_manually")
    await add(session, "Odd Co", ats_vendor="smartrecruiters", board_id="odd")
    await add(session, "Mystery Inc", resolution="unresolved")

    views = {v.name: v for v in await list_companies(CompaniesRepo(session), "all")}

    assert views["Acme"].board_status == "board"
    assert views["Pages Ltd"].board_status == "careers_page"
    assert views["Keka Co"].board_status == "check_manually"
    assert views["Odd Co"].board_status == "unsupported"
    assert views["Mystery Inc"].board_status == "unresolved"
    assert views["Acme"].origin == "built_in"


async def test_the_list_is_sorted_by_name(session: AsyncSession) -> None:
    for name in ("beta", "Alpha", "Gamma"):
        await add(session, name)

    names = [v.name for v in await list_companies(CompaniesRepo(session), "all")]

    assert names == ["Alpha", "beta", "Gamma"]


async def test_US3_AS4_hidden_company_not_fetched(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    company = await add(session, "Acme", ats_vendor="greenhouse", board_id="acme")
    assert [c.name for c in await repo.list_readable()] == ["Acme"]

    view = await hide_company(repo, company, hidden=True)
    await session.commit()

    assert view.hidden is True
    assert await repo.list_readable() == []
    assert [v.name for v in await list_companies(repo, "hidden")] == ["Acme"]
    assert [v.name for v in await list_companies(repo, "all")] == ["Acme"]  # still listed

    await hide_company(repo, company, hidden=False)
    await session.commit()
    assert [c.name for c in await repo.list_readable()] == ["Acme"]
    assert await list_companies(repo, "hidden") == []


async def test_FR016_only_user_rows_hard_deleted(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    mine = await add(session, "Mine")
    shipped = await add(session, "Shipped", origin="built_in", key="shipped")
    job = await JobsRepo(session).add(
        company_id=mine,
        company_name="Mine",
        title="Engineer",
        first_seen_at=NOW,
        last_seen_at=NOW,
        description="d",
        state="explore",
    )
    await session.commit()

    await delete_company(repo, mine, now=NOW)
    await delete_company(repo, shipped, now=NOW)
    await session.commit()

    assert await repo.get(mine) is None
    tombstone = await repo.get(shipped)
    assert tombstone is not None
    assert tombstone.deleted_at == NOW
    assert await list_companies(repo, "all") == []
    # the person's jobs from a deleted company stay
    kept = await session.scalar(select(JobRow.company_name).where(JobRow.id == job.id))
    assert kept == "Mine"
    assert await session.scalar(select(func.count()).select_from(CompanyRow)) == 1


async def test_a_deleted_built_in_row_is_not_listed_or_read(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    shipped = await add(
        session, "Shipped", origin="built_in", key="shipped", ats_vendor="lever", board_id="s"
    )

    await delete_company(repo, shipped, now=NOW)
    await session.commit()

    assert await repo.list_readable() == []
    assert await list_companies(repo, "hidden") == []


async def test_FR018_edit_sets_user_modified(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    company = await add(session, "Acme", origin="built_in", key="acme", city="Pune")

    view = await update_company(repo, company, {"name": "Acme Labs", "city": "Chennai"})
    await session.commit()

    assert (view.name, view.city, view.user_modified) == ("Acme Labs", "Chennai", True)
    stored = await repo.get(company)
    assert stored is not None
    assert stored.user_modified is True


async def test_hiding_alone_does_not_count_as_an_edit(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    company = await add(session, "Acme", origin="built_in", key="acme")

    view = await hide_company(repo, company, hidden=True)

    assert (view.hidden, view.user_modified) == (True, False)


async def test_an_edit_can_clear_an_optional_field(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    company = await add(session, "Acme", website="https://acme.example.com")

    view = await update_company(repo, company, {"website": ""})

    assert view.website is None


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "x" * 121}, "name"),
        ({"city": "x" * 81}, "city"),
        ({"website": "not a link"}, "website"),
        ({"careers_url": "ftp://x.example.com"}, "careers_url"),
        ({"careers_url": "https://x.example.com/" + "a" * 500}, "careers_url"),
    ],
)
async def test_invalid_edits_are_refused_with_field_messages(
    session: AsyncSession, changes: dict[str, object], field: str
) -> None:
    repo = CompaniesRepo(session)
    company = await add(session, "Acme")

    with pytest.raises(CompanyError) as raised:
        await update_company(repo, company, changes)

    assert [e.field for e in raised.value.errors] == [field]
    stored = await repo.get(company)
    assert stored is not None
    assert (stored.name, stored.user_modified) == ("Acme", False)


async def test_an_unknown_company_is_not_found(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    for call in (
        update_company(repo, UUID(int=9), {"name": "x"}),
        hide_company(repo, UUID(int=9), hidden=True),
        delete_company(repo, UUID(int=9), now=NOW),
    ):
        with pytest.raises(CompanyNotFoundError):
            await call


async def test_FR019_check_manually_list(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    await add(
        session, "Keka Co", resolution="check_manually", careers_url="https://keka.example.com/jobs"
    )
    await add(session, "Blocked Co", resolution="careers_page", last_check_result="blocked")
    await add(session, "Fine Co", ats_vendor="lever", board_id="fine", last_check_result="ok")
    deleted = await add(
        session, "Gone Co", origin="built_in", key="gone", resolution="check_manually"
    )
    await delete_company(repo, deleted, now=NOW)
    await session.commit()

    listed = await check_manually_list(repo)

    assert [v.name for v in listed] == ["Blocked Co", "Keka Co"]
    assert [v.name for v in await list_companies(repo, "check_manually")] == [
        "Blocked Co",
        "Keka Co",
    ]
    assert listed[1].careers_url == "https://keka.example.com/jobs"
