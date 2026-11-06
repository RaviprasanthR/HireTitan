"""Adding a company by its careers link, and finding its job board (US3-AS2, FR-017, R12).

Nothing found here is used until the person confirms it. Seeing the suggestion only reads the
board's job count; saving the board happens in :func:`confirm_board`, which works the board out
from the saved careers link again, so a caller can never save a board of its own choosing.

Deviation from the plan (W8 as a queued workflow): recognising a board address is a pure check of
the link and the job count is one board read, so it runs while the person waits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID

from hiretitan.search.application.companies import (
    CompaniesStore,
    CompanyError,
    CompanyNotFoundError,
    CompanyView,
    check_fields,
    view_of,
)
from hiretitan.search.application.paste import FieldIssue
from hiretitan.search.application.ports import BoardRef, CareerOpsPort, ScanOk
from hiretitan.search.domain.vendors import ENABLED_VENDORS


class DiscoveryError(ValueError):
    """There is no board that can be confirmed."""


class DiscoveryStore(CompaniesStore, Protocol):
    async def add(self, **fields: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class Suggestion:
    ats_vendor: str
    board_id: str
    supported: bool  # false for a provider HireTitan may not read (yet)
    live_jobs: int | None  # None when the board was not read or could not be read


@dataclass(frozen=True, slots=True)
class Discovery:
    status: Literal["found", "unsupported", "none"]
    suggestion: Suggestion | None


async def add_company(
    store: DiscoveryStore,
    *,
    name: str,
    careers_url: str,
    city: str | None = None,
    website: str | None = None,
) -> CompanyView:
    """A company of the person's own. It stays unresolved, and is not read, until they decide."""
    fields = {
        "name": name,
        "careers_url": careers_url,
        "city": city or "",
        "website": website or "",
    }
    problems: list[FieldIssue] = []
    try:
        values = check_fields(fields)
    except CompanyError as error:
        problems = list(error.errors)
        values = {}
    if not careers_url.strip():
        problems.append(FieldIssue("careers_url", "Add the link to the company's careers page."))
    if problems:
        raise CompanyError(problems)
    row = await store.add(origin="user", resolution="unresolved", **values)
    return view_of(row)


async def _company(store: DiscoveryStore, company_id: UUID) -> Any:
    row = await store.get(company_id)
    if row is None or row.deleted_at is not None:
        raise CompanyNotFoundError(str(company_id))
    return row


async def suggest_board(
    store: DiscoveryStore, careers: CareerOpsPort, company_id: UUID
) -> Discovery:
    """What board sits behind the careers link, and how many jobs it lists now. Saves nothing."""
    row = await _company(store, company_id)
    found = await careers.discover(row.careers_url) if row.careers_url else None
    if found is None:
        return Discovery("none", None)
    if found.vendor not in ENABLED_VENDORS:
        return Discovery("unsupported", Suggestion(found.vendor, found.board_id, False, None))
    scan = (await careers.scan([BoardRef(company_id, found.vendor, found.board_id)])).get(
        company_id
    )
    live = len(scan.postings) if isinstance(scan, ScanOk) else None
    return Discovery("found", Suggestion(found.vendor, found.board_id, True, live))


async def confirm_board(
    store: DiscoveryStore, careers: CareerOpsPort, company_id: UUID
) -> CompanyView:
    """Use the board behind the careers link. Only a provider we may read can be confirmed."""
    row = await _company(store, company_id)
    found = await careers.discover(row.careers_url) if row.careers_url else None
    if found is None or found.vendor not in ENABLED_VENDORS:
        raise DiscoveryError("There is no job board to confirm for this company.")
    await store.set_fields(
        company_id,
        ats_vendor=found.vendor,
        board_id=found.board_id,
        resolution="user_confirmed",
    )
    return view_of(await _company(store, company_id))


async def reject_board(
    store: DiscoveryStore, careers: CareerOpsPort, company_id: UUID
) -> CompanyView:
    """Do not use a board. The careers page is read instead; a provider we may not read, or a
    page that cannot be read later, ends up on the check-manually list."""
    row = await _company(store, company_id)
    found = await careers.discover(row.careers_url) if row.careers_url else None
    unreadable_board = found is not None and found.vendor not in ENABLED_VENDORS
    await store.set_fields(
        company_id, resolution="check_manually" if unreadable_board else "careers_page"
    )
    return view_of(await _company(store, company_id))
