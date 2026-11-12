"""The company list: what the person sees and what they can change (US3, FR-016 to FR-019).

A company is read only when it is not hidden, not deleted and has a readable board or careers
page. Editing a built-in company marks it ``user_modified`` so a later release of the shipped
list never overwrites the person's change (FR-018). Deleting a built-in company keeps a tombstone
so the loader does not bring it back; a company the person added is removed outright (FR-016).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from hiretitan.search.application.paste import FieldIssue
from hiretitan.search.domain.companies import BoardStatus, board_status

FILTERS: Final = ("all", "check_manually", "hidden")
NAME_MAX: Final = 120
CITY_MAX: Final = 80
URL_MAX: Final = 500
EDITABLE: Final = ("name", "city", "website", "careers_url")


class CompanyNotFoundError(LookupError):
    """There is no such company."""


class CompanyError(ValueError):
    """An edit was refused; nothing changed."""

    def __init__(self, errors: list[FieldIssue]) -> None:
        super().__init__("; ".join(e.message for e in errors))
        self.errors = errors


class StoredCompany(Protocol):
    id: UUID
    origin: str
    name: str
    city: str | None
    website: str | None
    careers_url: str | None
    ats_vendor: str | None
    board_id: str | None
    resolution: str
    hidden: bool
    user_modified: bool
    deleted_at: datetime | None
    last_checked_at: datetime | None
    last_check_result: str | None
    last_check_error: str | None


class CompaniesStore(Protocol):
    async def get(self, company_id: UUID) -> StoredCompany | None: ...

    async def list_filtered(self, filter: str) -> list[Any]: ...

    async def list_check_manually(self) -> list[Any]: ...

    async def set_fields(self, company_id: UUID, **fields: Any) -> None: ...

    async def remove(self, company_id: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class CompanyView:
    id: UUID
    origin: str
    name: str
    city: str | None
    website: str | None
    careers_url: str | None
    ats_vendor: str | None
    board_id: str | None
    resolution: str
    board_status: BoardStatus
    hidden: bool
    user_modified: bool
    last_checked_at: datetime | None
    last_check_result: str | None
    last_check_error: str | None
    # Filled only by the list (feature 002b); other responses carry the defaults.
    contact_count: int = 0
    has_note: bool = False
    note_preview: str | None = None  # the note on one line, shortened for the list row
    pipeline: Literal["applied", "inquired"] | None = None  # the furthest a job here has got


NOTE_PREVIEW_MAX = 120
NOTE_HEAD = NOTE_PREVIEW_MAX * 4  # enough text to fill the preview once spaces are collapsed


def note_preview(head: str | None) -> str | None:
    """One line, spaces collapsed, at most ``NOTE_PREVIEW_MAX`` characters, ending in an ellipsis
    when it was cut. ``head`` is the start of the note."""
    text = " ".join((head or "").split())
    if not text:
        return None
    if len(text) <= NOTE_PREVIEW_MAX:
        return text
    return text[: NOTE_PREVIEW_MAX - 1].rstrip() + "…"


def view_of(row: StoredCompany) -> CompanyView:
    return CompanyView(
        id=row.id,
        origin=row.origin,
        name=row.name,
        city=row.city,
        website=row.website,
        careers_url=row.careers_url,
        ats_vendor=row.ats_vendor,
        board_id=row.board_id,
        resolution=row.resolution,
        board_status=board_status(row.ats_vendor, row.resolution, row.last_check_result),
        hidden=row.hidden,
        user_modified=row.user_modified,
        last_checked_at=row.last_checked_at,
        last_check_result=row.last_check_result,
        last_check_error=row.last_check_error,
    )


async def _one(store: CompaniesStore, company_id: UUID) -> StoredCompany:
    row = await store.get(company_id)
    if row is None or row.deleted_at is not None:
        raise CompanyNotFoundError(str(company_id))
    return row


async def list_companies(
    store: CompaniesStore,
    filter: str = "all",
    counts: Mapping[UUID, tuple[int, bool]] | None = None,
    pipeline: Mapping[UUID, Literal["applied", "inquired"]] | None = None,
    note_heads: Mapping[UUID, str] | None = None,
) -> list[CompanyView]:
    """The company list.

    ``counts`` maps a company id to (contact count, has a note); ``pipeline`` maps a company id to
    ``applied`` (a job there is applied) or ``inquired`` (the person asked about one); companies
    with neither are left out.
    """
    known = counts or {}
    in_pipeline = pipeline or {}
    heads = note_heads or {}
    views = []
    for row in await store.list_filtered(filter):
        contact_count, has_note = known.get(row.id, (0, False))
        views.append(
            replace(
                view_of(row),
                contact_count=contact_count,
                has_note=has_note,
                note_preview=note_preview(heads.get(row.id)),
                pipeline=in_pipeline.get(row.id),
            )
        )
    return views


async def check_manually_list(store: CompaniesStore) -> list[CompanyView]:
    """Companies the person has to look at themselves (FR-019)."""
    return [view_of(row) for row in await store.list_check_manually()]


def _web_link(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc) and " " not in value


def check_fields(changes: dict[str, Any]) -> dict[str, Any]:
    errors: list[FieldIssue] = []
    values: dict[str, Any] = {}
    for field in EDITABLE:
        if field not in changes:
            continue
        text = (changes[field] or "").strip()
        if field == "name":
            if not text:
                errors.append(FieldIssue(field, "The company needs a name."))
            elif len(text) > NAME_MAX:
                errors.append(FieldIssue(field, f"The name can be at most {NAME_MAX} characters."))
        elif field == "city":
            if len(text) > CITY_MAX:
                errors.append(FieldIssue(field, f"The city can be at most {CITY_MAX} characters."))
        elif text and len(text) > URL_MAX:
            errors.append(FieldIssue(field, f"The link can be at most {URL_MAX} characters."))
        elif text and not _web_link(text):
            errors.append(FieldIssue(field, "The link must start with http:// or https://."))
        values[field] = text or None
    if errors:
        raise CompanyError(errors)
    return values


async def update_company(
    store: CompaniesStore, company_id: UUID, changes: dict[str, Any]
) -> CompanyView:
    """Edit name, city, website or careers link. Marks the company as edited by the person."""
    await _one(store, company_id)
    values = check_fields(changes)
    if values:
        await store.set_fields(company_id, user_modified=True, **values)
    return view_of(await _one(store, company_id))


async def hide_company(store: CompaniesStore, company_id: UUID, *, hidden: bool) -> CompanyView:
    """A hidden company stays in the list but is never read by a search (US3 AS4)."""
    await _one(store, company_id)
    await store.set_fields(company_id, hidden=hidden)
    return view_of(await _one(store, company_id))


async def delete_company(store: CompaniesStore, company_id: UUID, *, now: datetime) -> None:
    row = await _one(store, company_id)
    if row.origin == "user":
        await store.remove(company_id)
    else:
        await store.set_fields(company_id, deleted_at=now)
