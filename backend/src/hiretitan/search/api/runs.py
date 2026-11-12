"""Search run endpoints (contracts/rest-api.md, "Search runs")."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.api.models import JobCardPage, job_cards
from hiretitan.search.application.ports import ProposalSource
from hiretitan.search.application.rules import RulesNotApprovedError, RulesService
from hiretitan.search.application.search import (
    RunQueue,
    SearchAlreadyRunningError,
    SearchNotRunningError,
    SetupGate,
    SetupIncompleteError,
    request_stop,
    start_search,
)
from hiretitan.search.infra.models import (
    CompanyRow,
    JobRow,
    RelevanceDecisionRow,
    SearchRunCompanyRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import RuleSetsRepo, SearchRunsRepo
from hiretitan.search.infra.search_store import SearchStore

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


@dataclass(frozen=True)
class SearchRunsApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    queue: RunQueue
    clock: ClockPort
    source: Callable[[AsyncSession], ProposalSource]
    synonyms: Mapping[str, tuple[str, ...]]
    setup_gate: Callable[[AsyncSession], SetupGate]


class StartIn(BaseModel):
    mode: Literal["rules_and_ai", "rules_only"] = "rules_and_ai"


class StartedOut(BaseModel):
    search_run_id: UUID
    run_id: UUID


class CompanyResultOut(BaseModel):
    company_id: UUID
    company_name: str
    batch_no: int
    result: str
    jobs_found: int
    error: str | None


class SearchRunSummary(BaseModel):
    id: UUID
    run_id: UUID
    mode: str
    outcome: str | None
    stop_message: str | None
    stop_requested: bool
    batches_done: int
    companies_total: int
    companies_read: int
    jobs_found: int
    skipped_by_rules: int
    judged_by_ai: int
    kept: int
    added: int
    merged: int
    not_checked_by_ai: int
    ai_note: str | None
    started_at: datetime | None
    finished_at: datetime | None


class SearchRunOut(SearchRunSummary):
    companies: list[CompanyResultOut]


class SearchRunPage(BaseModel):
    items: list[SearchRunSummary]
    next_cursor: str | None = None


def ai_note(row: SearchRunRow) -> str | None:
    """Say plainly when the AI step did not run, and why (US1 AS7)."""
    if row.mode == "rules_only":
        return "AI step skipped: you chose rules only."
    if row.judged_by_ai == 0 and row.not_checked_by_ai > 0:
        return "AI step skipped: the AI was not available, so the rules alone decided."
    return None


def summary(row: SearchRunRow) -> SearchRunSummary:
    return SearchRunSummary(
        id=row.id,
        run_id=row.workflow_run_id,
        mode=row.mode,
        outcome=row.outcome,
        stop_message=row.stop_message,
        stop_requested=row.stop_requested,
        batches_done=row.batches_done,
        companies_total=len(row.company_order),
        companies_read=row.next_index,
        jobs_found=row.jobs_found,
        skipped_by_rules=row.skipped_by_rules,
        judged_by_ai=row.judged_by_ai,
        kept=row.kept,
        added=row.added,
        merged=row.merged,
        not_checked_by_ai=row.not_checked_by_ai,
        ai_note=ai_note(row),
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _not_found() -> ProblemError:
    return ProblemError(404, "That search does not exist.")


def create_search_runs_router(deps: SearchRunsApiDeps) -> APIRouter:
    router = APIRouter(prefix="/search", tags=["search"])

    async def get_run(session: AsyncSession, search_run_id: UUID) -> SearchRunRow:
        row = await SearchRunsRepo(session).get(search_run_id)
        if row is None:
            raise _not_found()
        return row

    @router.post("/runs", status_code=202)
    async def start(body: StartIn) -> StartedOut:
        async with deps.sessions() as session:
            rules = RulesService(RuleSetsRepo(session), deps.source(session), deps.synonyms)
            try:
                started = await start_search(
                    body.mode,
                    rules=rules,
                    setup=deps.setup_gate(session),
                    store=SearchStore(session),
                    queue=deps.queue,
                    now=deps.clock.now(),
                )
            except RulesNotApprovedError as error:
                raise ProblemError(
                    409, "Approve your search rules first.", reason="rules_not_approved"
                ) from error
            except SetupIncompleteError as error:
                raise ProblemError(
                    409, "Finish setup before searching.", reason="setup_incomplete"
                ) from error
            except SearchAlreadyRunningError as error:
                raise ProblemError(
                    409, "A search is already running.", reason="search_already_running"
                ) from error
            return StartedOut(search_run_id=started.search_run_id, run_id=started.run_id)

    @router.post("/runs/{search_run_id}/stop", status_code=202)
    async def stop(search_run_id: UUID) -> dict[str, bool]:
        async with deps.sessions() as session:
            await get_run(session, search_run_id)
            try:
                await request_stop(SearchStore(session), search_run_id)
            except SearchNotRunningError as error:
                raise ProblemError(409, "That search is not running.") from error
            return {"stopping": True}

    @router.get("/runs/{search_run_id}")
    async def read_run(search_run_id: UUID) -> SearchRunOut:
        async with deps.sessions() as session:
            row = await get_run(session, search_run_id)
            results = await session.execute(
                select(SearchRunCompanyRow, CompanyRow.name)
                .join(CompanyRow, CompanyRow.id == SearchRunCompanyRow.company_id)
                .where(SearchRunCompanyRow.search_run_id == search_run_id)
                .order_by(SearchRunCompanyRow.batch_no, CompanyRow.name)
            )
            companies = [
                CompanyResultOut(
                    company_id=r.company_id,
                    company_name=name,
                    batch_no=r.batch_no,
                    result=r.result,
                    jobs_found=r.jobs_found,
                    error=r.error,
                )
                for r, name in results.all()
            ]
            return SearchRunOut(**summary(row).model_dump(), companies=companies)

    @router.get("/runs")
    async def history(limit: int = DEFAULT_LIMIT, cursor: str | None = None) -> SearchRunPage:
        limit = max(1, min(limit, MAX_LIMIT))
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        async with deps.sessions() as session:
            rows = list(
                await session.scalars(
                    select(SearchRunRow)
                    .order_by(SearchRunRow.created_at.desc(), SearchRunRow.id.desc())
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
        more = len(rows) > limit
        return SearchRunPage(
            items=[summary(r) for r in rows[:limit]],
            next_cursor=str(offset + limit) if more else None,
        )

    @router.get("/runs/{search_run_id}/skipped")
    async def skipped(
        search_run_id: UUID, limit: int = DEFAULT_LIMIT, cursor: str | None = None
    ) -> JobCardPage:
        limit = max(1, min(limit, MAX_LIMIT))
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        async with deps.sessions() as session:
            await get_run(session, search_run_id)
            rows = list(
                await session.scalars(
                    select(JobRow)
                    .join(RelevanceDecisionRow, RelevanceDecisionRow.job_id == JobRow.id)
                    .where(
                        RelevanceDecisionRow.search_run_id == search_run_id,
                        RelevanceDecisionRow.outcome == "skipped",
                        RelevanceDecisionRow.is_current,
                        JobRow.state == "skipped",
                    )
                    .order_by(JobRow.sort_key.desc(), JobRow.id)
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            more = len(rows) > limit
            return JobCardPage(
                items=await job_cards(session, rows[:limit]),
                next_cursor=str(offset + limit) if more else None,
            )

    @router.get("/latest")
    async def latest() -> SearchRunSummary | None:
        async with deps.sessions() as session:
            row = await SearchRunsRepo(session).latest()
            return summary(row) if row is not None else None

    return router
