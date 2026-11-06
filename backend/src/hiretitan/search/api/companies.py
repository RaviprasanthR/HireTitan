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
    CompanyError,
    CompanyNotFoundError,
    CompanyView,
    delete_company,
    hide_company,
    list_companies,
    update_company,
)
from hiretitan.search.infra.repos import CompaniesRepo


@dataclass(frozen=True)
class SearchCompaniesApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    clock: ClockPort


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


class CompanyPage(BaseModel):
    items: list[CompanyOut]
    next_cursor: str | None = None


class CompanyPatch(BaseModel):
    """Only the fields that are sent change; an empty text clears an optional field."""

    name: str | None = None
    city: str | None = None
    website: str | None = None
    careers_url: str | None = None
    hidden: bool | None = None


def out(view: CompanyView) -> CompanyOut:
    return CompanyOut(**asdict(view))


def _not_found() -> ProblemError:
    return ProblemError(404, "That company does not exist.")


def create_companies_router(deps: SearchCompaniesApiDeps) -> APIRouter:
    router = APIRouter(prefix="/companies", tags=["companies"])

    @router.get("", response_model=CompanyPage)
    async def companies(filter: Literal["all", "check_manually", "hidden"] = "all") -> CompanyPage:
        async with deps.sessions() as session:
            views = await list_companies(CompaniesRepo(session), filter)
        return CompanyPage(items=[out(v) for v in views])

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
                return problem(
                    422,
                    str(error),
                    errors=[{"field": e.field, "message": e.message} for e in error.errors],
                )
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
