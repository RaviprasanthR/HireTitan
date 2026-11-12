"""Companies endpoints (contracts/rest-api.md, "Companies"): the list, edit, hide and delete."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError, problem
from hiretitan.search.application.companies import (
    EDITABLE,
    NOTE_HEAD,
    CompanyError,
    CompanyNotFoundError,
    CompanyView,
    delete_company,
    hide_company,
    list_companies,
    update_company,
)
from hiretitan.search.application.discovery import (
    DiscoveryError,
    add_company,
    confirm_board,
    reject_board,
    suggest_board,
)
from hiretitan.search.application.ports import CareerOpsPort
from hiretitan.search.infra.repos import (
    AppliedCompaniesRepo,
    CompaniesRepo,
    ContactsRepo,
    NotesRepo,
)


@dataclass(frozen=True)
class SearchCompaniesApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    clock: ClockPort
    careers: CareerOpsPort


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
    note_preview: str | None = None
    has_application: bool = False


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
            applied = await AppliedCompaniesRepo(session).company_ids()
            heads = await NotesRepo(session).heads(NOTE_HEAD)
            views = await list_companies(CompaniesRepo(session), filter, counts, applied, heads)
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
