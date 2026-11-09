"""T050: adding a company by its careers link and confirming the suggested board
(US3-AS2, FR-017, research R12)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.search.application.companies import CompanyError, CompanyNotFoundError
from hiretitan.search.application.discovery import (
    DiscoveryError,
    add_company,
    confirm_board,
    reject_board,
    suggest_board,
)
from hiretitan.search.application.ports import (
    BoardRef,
    DiscoveryResult,
    Posting,
    ScanError,
    ScanOk,
    ScanResult,
)
from hiretitan.search.infra.careerops.boards import discover_board
from hiretitan.search.infra.repos import CompaniesRepo

GREENHOUSE = "https://job-boards.greenhouse.io/acme"


class StubCareerOps:
    """Recognises addresses like the real adapter; reads boards from a script."""

    def __init__(self) -> None:
        self.live = 3
        self.fail = False
        self.found: DiscoveryResult | str | None = "real"
        self.scanned: list[BoardRef] = []

    async def scan(self, refs: list[BoardRef]) -> ScanResult:
        self.scanned += refs
        result: ScanResult = {}
        for ref in refs:
            result[ref.company_id] = (
                ScanError("board unreachable")
                if self.fail
                else ScanOk(
                    [Posting(f"Job {i}", f"https://x.example/{i}") for i in range(self.live)]
                )
            )
        return result

    async def discover(self, careers_url: str) -> DiscoveryResult | None:
        if self.found == "real":
            return discover_board(careers_url)
        assert not isinstance(self.found, str)
        return self.found


@pytest.fixture
async def session(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessions() as session:
        yield session


async def added(session: AsyncSession, careers_url: str = GREENHOUSE, name: str = "Acme") -> UUID:
    view = await add_company(CompaniesRepo(session), name=name, careers_url=careers_url)
    await session.commit()
    return view.id


async def test_a_new_company_starts_unresolved_and_is_not_read(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    company = await added(session)

    row = await repo.get(company)
    assert row is not None
    assert (row.origin, row.resolution, row.ats_vendor, row.board_id) == (
        "user",
        "unresolved",
        None,
        None,
    )
    assert row.careers_url == GREENHOUSE
    assert await repo.list_readable() == []


async def test_US3_AS2_match_used_only_after_confirm(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    careers = StubCareerOps()
    company = await added(session)

    found = await suggest_board(repo, careers, company)

    assert found.status == "found"
    assert found.suggestion is not None
    assert (found.suggestion.ats_vendor, found.suggestion.board_id) == ("greenhouse", "acme")
    assert found.suggestion.live_jobs == 3
    assert await repo.list_readable() == []  # shown, not used yet

    view = await confirm_board(repo, careers, company)
    await session.commit()

    assert (view.ats_vendor, view.board_id, view.resolution) == (
        "greenhouse",
        "acme",
        "user_confirmed",
    )
    assert view.board_status == "board"
    assert [c.name for c in await repo.list_readable()] == ["Acme"]


async def test_FR017_unconfirmed_board_is_never_fetched(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    careers = StubCareerOps()
    company = await added(session)

    await suggest_board(repo, careers, company)
    await suggest_board(repo, careers, company)

    row = await repo.get(company)
    assert row is not None
    assert (row.ats_vendor, row.board_id, row.resolution) == (None, None, "unresolved")
    assert await repo.list_readable() == []
    # looking at the suggestion reads the board for its job count, one company at a time
    assert {ref.company_id for ref in careers.scanned} == {company}


async def test_the_board_to_confirm_comes_from_the_link_not_the_caller(
    session: AsyncSession,
) -> None:
    repo = CompaniesRepo(session)
    careers = StubCareerOps()
    company = await added(session, "https://jobs.lever.co/zeta", "Zeta")

    view = await confirm_board(repo, careers, company)

    assert (view.ats_vendor, view.board_id) == ("lever", "zeta")


async def test_reject_falls_back_to_careers_page(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    company = await added(session)

    view = await reject_board(repo, StubCareerOps(), company)
    await session.commit()

    assert (view.resolution, view.ats_vendor, view.board_id) == ("careers_page", None, None)
    assert view.careers_url == GREENHOUSE
    assert view.board_status == "careers_page"


async def test_a_link_with_no_known_board_can_only_be_rejected(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    careers = StubCareerOps()
    company = await added(session, "https://www.example.com/careers")

    found = await suggest_board(repo, careers, company)
    assert (found.status, found.suggestion) == ("none", None)
    with pytest.raises(DiscoveryError):
        await confirm_board(repo, careers, company)

    view = await reject_board(repo, careers, company)
    assert view.resolution == "careers_page"


async def test_unsupported_vendor_falls_back(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    careers = StubCareerOps()
    careers.found = DiscoveryResult("smartrecruiters", "acme")
    company = await added(session)

    found = await suggest_board(repo, careers, company)
    assert found.status == "unsupported"
    assert found.suggestion is not None
    assert found.suggestion.supported is False
    assert found.suggestion.live_jobs is None
    assert careers.scanned == []  # a provider we may not read is never read
    with pytest.raises(DiscoveryError):
        await confirm_board(repo, careers, company)

    view = await reject_board(repo, careers, company)
    assert (view.resolution, view.board_status) == ("check_manually", "check_manually")
    assert await repo.list_readable() == []


async def test_a_board_that_cannot_be_read_still_shows_the_match(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    careers = StubCareerOps()
    careers.fail = True
    company = await added(session)

    found = await suggest_board(repo, careers, company)

    assert found.status == "found"
    assert found.suggestion is not None
    assert found.suggestion.live_jobs is None


async def test_the_company_needs_a_name_and_a_careers_link(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)

    with pytest.raises(CompanyError) as raised:
        await add_company(repo, name="", careers_url="")
    assert [e.field for e in raised.value.errors] == ["name", "careers_url"]

    with pytest.raises(CompanyError) as raised:
        await add_company(repo, name="Acme", careers_url="ftp://x.example.com")
    assert [e.field for e in raised.value.errors] == ["careers_url"]

    assert await repo.list_all() == []


async def test_optional_city_and_website_are_kept(session: AsyncSession) -> None:
    view = await add_company(
        CompaniesRepo(session),
        name="Acme",
        careers_url=GREENHOUSE,
        city="Pune",
        website="https://acme.example.com",
    )

    assert (view.city, view.website) == ("Pune", "https://acme.example.com")


async def test_an_unknown_company_is_not_found(session: AsyncSession) -> None:
    repo = CompaniesRepo(session)
    careers = StubCareerOps()
    for call in (
        suggest_board(repo, careers, UUID(int=3)),
        confirm_board(repo, careers, UUID(int=3)),
        reject_board(repo, careers, UUID(int=3)),
    ):
        with pytest.raises(CompanyNotFoundError):
            await call
