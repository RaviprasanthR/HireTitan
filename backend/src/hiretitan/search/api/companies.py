"""Companies endpoints (contracts/rest-api.md, "Companies"): the list, edit, hide and delete."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError, problem
from hiretitan.search.application.companies import (
    EDITABLE,
    CompanyError,
    CompanyNotFoundError,
    CompanyView,
    delete_company,
    hide_company,
    list_companies,
    update_company,
)
from hiretitan.search.application.companies_csv import (
    MAX_BYTES,
    MAX_ROWS,
    CsvFileError,
    ImportPlan,
    apply_import,
    export_csv,
    preview_import,
)
from hiretitan.search.application.discovery import (
    DiscoveryError,
    add_company,
    confirm_board,
    reject_board,
    suggest_board,
)
from hiretitan.search.application.ports import CareerOpsPort
from hiretitan.search.application.sheet_import import (
    RowIssue,
    SheetOutcome,
    apply_sheet,
    preview_sheet,
)
from hiretitan.search.domain.sheet import SheetError, SheetLayout, SheetRow, read
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo

PREVIEW_LIFETIME = timedelta(minutes=30)
PREVIEWS_KEPT = 10
CHUNK = 64 * 1024


class ImportPreviews:
    """Previewed CSV imports waiting for a Confirm. Held in memory: one person, one process,
    and a lost preview just means uploading the file again."""

    def __init__(self) -> None:
        self._held: dict[str, tuple[datetime, object]] = {}

    def hold(self, plan: object, now: datetime) -> str:
        self._held = {t: v for t, v in self._held.items() if v[0] > now}
        while len(self._held) >= PREVIEWS_KEPT:
            del self._held[next(iter(self._held))]
        token = secrets.token_urlsafe(24)
        self._held[token] = (now + PREVIEW_LIFETIME, plan)
        return token

    def take(self, token: str, now: datetime) -> object | None:
        """The held plan (a company CSV's rows or a sheet), once; callers check which kind."""
        held = self._held.pop(token, None)
        return held[1] if held is not None and held[0] > now else None


@dataclass(frozen=True, slots=True)
class HeldSheet:
    """A previewed company sheet: the rows are applied on Confirm."""

    layout: SheetLayout
    rows: list[SheetRow]


@dataclass(frozen=True)
class SearchCompaniesApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    clock: ClockPort
    careers: CareerOpsPort
    previews: ImportPreviews = field(default_factory=ImportPreviews)


class CompanyOut(BaseModel):
    id: UUID
    origin: str
    name: str
    city: str | None
    website: str | None
    careers_url: str | None
    ats_vendor: str | None
    board_id: str | None
    resolution: str
    board_status: Literal["board", "careers_page", "check_manually", "unsupported", "unresolved"]
    hidden: bool
    user_modified: bool
    last_checked_at: datetime | None
    last_check_result: str | None
    last_check_error: str | None
    # Filled by the list only; the other responses carry 0, false and null.
    contact_count: int = 0
    has_note: bool = False
    openings: dict[str, int] | None = None


class CompanyPage(BaseModel):
    items: list[CompanyOut]
    next_cursor: str | None = None


class CompanyIn(BaseModel):
    # defaults, so a missing field is reported by the use case, field by field
    name: str = ""
    careers_url: str = ""
    city: str | None = None
    website: str | None = None


class SuggestionOut(BaseModel):
    ats_vendor: str
    board_id: str
    supported: bool
    live_jobs: int | None


class DiscoveryOut(BaseModel):
    status: Literal["found", "unsupported", "none"]
    suggestion: SuggestionOut | None


class CompanyPatch(BaseModel):
    """Only the fields that are sent change; an empty text clears an optional field."""

    name: str | None = None
    city: str | None = None
    website: str | None = None
    careers_url: str | None = None
    hidden: bool | None = None


class ImportRowOut(BaseModel):
    row: int
    name: str
    city: str | None
    website: str | None
    careers_url: str | None
    ats_vendor: str | None
    board_id: str | None
    hidden: bool | None


class ImportUpdateOut(BaseModel):
    row: int
    id: UUID
    name: str
    changes: dict[str, dict[str, Any]]


class InvalidRowOut(BaseModel):
    row: int
    reason: str


class ImportPreview(BaseModel):
    add: list[ImportRowOut]
    update: list[ImportUpdateOut]
    invalid: list[InvalidRowOut]
    token: str


class ImportResult(BaseModel):
    added: int
    updated: int


class SheetColumnsOut(BaseModel):
    used: list[str]
    ignored: list[str]


class SheetCompaniesOut(BaseModel):
    matched: int
    to_add: int


class SheetContactsOut(BaseModel):
    to_add: int
    to_update: int


class SheetNotesOut(BaseModel):
    to_set: int
    to_change: int
    kept_yours: int


class SheetRowOut(BaseModel):
    line: int
    company: str
    action: Literal["matched", "add", "skip"]
    contacts_add: int
    contacts_update: int
    notes: Literal["set", "changed", "kept", "none"]
    shortened: bool


class SheetIssueOut(BaseModel):
    line: int
    reason: str


class SheetPreview(BaseModel):
    token: str
    columns: SheetColumnsOut
    companies: SheetCompaniesOut
    contacts: SheetContactsOut
    notes: SheetNotesOut
    rows: list[SheetRowOut]
    skipped: list[SheetIssueOut]
    shortened: list[SheetIssueOut]


class SheetResult(BaseModel):
    matched: int
    companies_added: int
    contacts_added: int
    contacts_updated: int
    notes_set: int
    notes_changed: int
    notes_kept: int
    skipped: list[SheetIssueOut]
    shortened: list[SheetIssueOut]


def _issues(issues: tuple[RowIssue, ...]) -> list[SheetIssueOut]:
    return [SheetIssueOut(line=i.line, reason=i.reason) for i in issues]


def _sheet_preview_of(outcome: SheetOutcome, token: str) -> SheetPreview:
    return SheetPreview(
        token=token,
        columns=SheetColumnsOut(
            used=list(outcome.layout.used), ignored=list(outcome.layout.ignored)
        ),
        companies=SheetCompaniesOut(matched=outcome.matched, to_add=outcome.companies_added),
        contacts=SheetContactsOut(
            to_add=outcome.contacts_added, to_update=outcome.contacts_updated
        ),
        notes=SheetNotesOut(
            to_set=outcome.notes_set,
            to_change=outcome.notes_changed,
            kept_yours=outcome.notes_kept,
        ),
        rows=[
            SheetRowOut(
                line=r.line,
                company=r.company,
                action=r.action,
                contacts_add=r.contacts_add,
                contacts_update=r.contacts_update,
                notes=r.note,
                shortened=r.shortened,
            )
            for r in outcome.rows
        ],
        skipped=_issues(outcome.skipped),
        shortened=_issues(outcome.shortened),
    )


def _sheet_result_of(outcome: SheetOutcome) -> SheetResult:
    return SheetResult(
        matched=outcome.matched,
        companies_added=outcome.companies_added,
        contacts_added=outcome.contacts_added,
        contacts_updated=outcome.contacts_updated,
        notes_set=outcome.notes_set,
        notes_changed=outcome.notes_changed,
        notes_kept=outcome.notes_kept,
        skipped=_issues(outcome.skipped),
        shortened=_issues(outcome.shortened),
    )


def _sheet_text(filename: str | None, data: bytes) -> str:
    """The sheet as text, or a 415 when the file is not a CSV (checked before anything is read)."""
    if not (filename or "").lower().endswith(".csv"):
        raise ProblemError(415, "Save the sheet as a CSV file and upload that.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ProblemError(415, "This is not a text (CSV) file.") from error
    if "\x00" in text:
        raise ProblemError(415, "This is not a text (CSV) file.")
    return text


def _preview_of(plan: ImportPlan, token: str) -> ImportPreview:
    return ImportPreview(
        add=[
            ImportRowOut(
                row=r.line,
                name=r.name,
                city=r.city,
                website=r.website,
                careers_url=r.careers_url,
                ats_vendor=r.ats_vendor,
                board_id=r.board_id,
                hidden=r.hidden,
            )
            for r in plan.add
        ],
        update=[
            ImportUpdateOut(
                row=u.line,
                id=u.company_id,
                name=u.name,
                changes={k: {"from": c.before, "to": c.after} for k, c in u.changes.items()},
            )
            for u in plan.update
        ],
        invalid=[InvalidRowOut(row=i.line, reason=i.reason) for i in plan.invalid],
        token=token,
    )


async def _read_csv(file: UploadFile) -> bytes:
    parts: list[bytes] = []
    total = 0
    while chunk := await file.read(CHUNK):
        total += len(chunk)
        if total > MAX_BYTES:
            raise ProblemError(413, "The file is larger than 1 MB.")
        parts.append(chunk)
    return b"".join(parts)


def out(view: CompanyView) -> CompanyOut:
    return CompanyOut(**asdict(view))


def _invalid(error: CompanyError) -> Any:
    return problem(
        422,
        str(error),
        errors=[{"field": e.field, "message": e.message} for e in error.errors],
    )


def _not_found() -> ProblemError:
    return ProblemError(404, "That company does not exist.")


def create_companies_router(deps: SearchCompaniesApiDeps) -> APIRouter:
    router = APIRouter(prefix="/companies", tags=["companies"])

    @router.get("", response_model=CompanyPage)
    async def companies(filter: Literal["all", "check_manually", "hidden"] = "all") -> CompanyPage:
        async with deps.sessions() as session:
            counts = await ContactsRepo(session).counts_by_company()
            views = await list_companies(CompaniesRepo(session), filter, counts)
        return CompanyPage(items=[out(v) for v in views])

    @router.post("", response_model=CompanyOut, status_code=201)
    async def create(body: CompanyIn) -> Any:
        async with deps.sessions() as session:
            try:
                view = await add_company(
                    CompaniesRepo(session),
                    name=body.name,
                    careers_url=body.careers_url,
                    city=body.city,
                    website=body.website,
                )
            except CompanyError as error:
                return _invalid(error)
            await session.commit()
        return out(view)

    @router.get("/export")
    async def export() -> Response:
        async with deps.sessions() as session:
            rows = await CompaniesRepo(session).list_all()
        return Response(
            export_csv(list(rows)),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="companies.csv"'},
        )

    @router.post("/import", response_model=ImportPreview)
    async def import_preview(file: UploadFile) -> ImportPreview:
        data = await _read_csv(file)
        async with deps.sessions() as session:
            try:
                plan, rows = await preview_import(CompaniesRepo(session), data)
            except CsvFileError as error:
                raise ProblemError(error.status, str(error)) from error
        return _preview_of(plan, deps.previews.hold(rows, deps.clock.now()))

    @router.post("/import/{token}/confirm", response_model=ImportResult)
    async def import_confirm(token: str) -> ImportResult:
        rows = deps.previews.take(token, deps.clock.now())
        if not isinstance(rows, list):
            raise ProblemError(404, "That import has expired. Upload the file again.")
        async with deps.sessions() as session:
            added, updated = await apply_import(CompaniesRepo(session), rows)
            await session.commit()
        return ImportResult(added=added, updated=updated)

    @router.post("/sheet-import", response_model=SheetPreview)
    async def sheet_preview(file: UploadFile) -> SheetPreview:
        data = await _read_csv(file)
        source = _sheet_text(file.filename, data)
        try:
            layout, rows = read(source)
        except SheetError as error:
            raise ProblemError(422, str(error), headers=list(error.headers)) from error
        if len(rows) > MAX_ROWS:
            raise ProblemError(422, "The file has more than 2,000 rows.")
        async with deps.sessions() as session:
            outcome = await preview_sheet(
                CompaniesRepo(session), ContactsRepo(session), NotesRepo(session), layout, rows
            )
        token = deps.previews.hold(HeldSheet(layout, rows), deps.clock.now())
        return _sheet_preview_of(outcome, token)

    @router.post("/sheet-import/{token}/confirm", response_model=SheetResult)
    async def sheet_confirm(token: str) -> SheetResult:
        held = deps.previews.take(token, deps.clock.now())
        if not isinstance(held, HeldSheet):
            raise ProblemError(404, "That import has expired. Upload the file again.")
        async with deps.sessions() as session:
            outcome = await apply_sheet(
                CompaniesRepo(session),
                ContactsRepo(session),
                NotesRepo(session),
                held.layout,
                held.rows,
            )
            await session.commit()
        return _sheet_result_of(outcome)

    @router.get("/{company_id}/discovery", response_model=DiscoveryOut)
    async def discovery(company_id: UUID) -> DiscoveryOut:
        async with deps.sessions() as session:
            try:
                found = await suggest_board(CompaniesRepo(session), deps.careers, company_id)
            except CompanyNotFoundError as error:
                raise _not_found() from error
        return DiscoveryOut(
            status=found.status,
            suggestion=SuggestionOut(**asdict(found.suggestion)) if found.suggestion else None,
        )

    @router.post("/{company_id}/discovery/confirm", response_model=CompanyOut)
    async def confirm(company_id: UUID) -> CompanyOut:
        async with deps.sessions() as session:
            try:
                view = await confirm_board(CompaniesRepo(session), deps.careers, company_id)
            except CompanyNotFoundError as error:
                raise _not_found() from error
            except DiscoveryError as error:
                raise ProblemError(409, str(error), reason="no_board") from error
            await session.commit()
        return out(view)

    @router.post("/{company_id}/discovery/reject", response_model=CompanyOut)
    async def reject(company_id: UUID) -> CompanyOut:
        async with deps.sessions() as session:
            try:
                view = await reject_board(CompaniesRepo(session), deps.careers, company_id)
            except CompanyNotFoundError as error:
                raise _not_found() from error
            await session.commit()
        return out(view)

    @router.patch("/{company_id}", response_model=CompanyOut)
    async def patch(company_id: UUID, body: CompanyPatch) -> Any:
        sent = body.model_fields_set
        async with deps.sessions() as session:
            repo = CompaniesRepo(session)
            try:
                changes: dict[str, Any] = {
                    name: getattr(body, name) for name in EDITABLE if name in sent
                }
                view = await update_company(repo, company_id, changes)
                if body.hidden is not None:
                    view = await hide_company(repo, company_id, hidden=body.hidden)
            except CompanyNotFoundError as error:
                raise _not_found() from error
            except CompanyError as error:
                return _invalid(error)
            await session.commit()
        return out(view)

    @router.delete("/{company_id}", status_code=204)
    async def delete(company_id: UUID) -> Response:
        async with deps.sessions() as session:
            try:
                await delete_company(CompaniesRepo(session), company_id, now=deps.clock.now())
            except CompanyNotFoundError as error:
                raise _not_found() from error
            await session.commit()
        return Response(status_code=204)

    return router
