"""Jobs endpoints (contracts/rest-api.md, "Jobs"): the lists, one job, restore, re-check, delete."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.api.models import DecisionOut, JobCardOut, JobCardPage, job_cards
from hiretitan.search.application.search import RunQueue
from hiretitan.search.domain.job_state import IllegalJobTransitionError, JobState, transition
from hiretitan.search.infra.models import JobRow, JobSourceRow
from hiretitan.search.infra.repos import Cursor, DecisionsRepo, JobFilters, JobsRepo
from hiretitan.search.workflow.recheck import RECHECK_WORKFLOW

DEFAULT_LIMIT = 25
RECHECKABLE = "rules_only_fallback"


@dataclass(frozen=True)
class SearchJobsApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    queue: RunQueue
    clock: ClockPort


class DecisionHistoryOut(DecisionOut):
    created_at: datetime
    is_current: bool
    prompt_name: str | None
    prompt_version: str | None
    provider: str | None
    model: str | None


class JobDetailOut(JobCardOut):
    description: str
    city: str | None
    country: str | None
    skills_found: list[str]
    years_found: Decimal | None
    canonical_url: str | None
    injection_flags: list[dict[str, Any]]
    decision_history: list[DecisionHistoryOut]
    first_search_id: UUID | None


def _encode(cursor: Cursor) -> str:
    value = (
        cursor.sort_value.isoformat()
        if isinstance(cursor.sort_value, datetime)
        else cursor.sort_value
    )
    raw = json.dumps(
        {"v": value, "id": str(cursor.id), "t": isinstance(cursor.sort_value, datetime)}
    )
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(token: str) -> Cursor:
    try:
        data = json.loads(base64.urlsafe_b64decode(token.encode()))
        value = datetime.fromisoformat(data["v"]) if data["t"] else str(data["v"])
        return Cursor(value, UUID(data["id"]))
    except (ValueError, KeyError, TypeError, binascii.Error) as error:
        raise ProblemError(422, "That page marker is not valid.") from error


def _not_found() -> ProblemError:
    return ProblemError(404, "That job does not exist.")


def create_search_jobs_router(deps: SearchJobsApiDeps) -> APIRouter:
    router = APIRouter(prefix="/jobs", tags=["jobs"])

    async def load(session: AsyncSession, job_id: UUID, *, deleted_ok: bool = False) -> JobRow:
        row = await JobsRepo(session).get(job_id)
        if row is None or (row.state == "deleted" and not deleted_ok):
            raise _not_found()
        return row

    async def detail(session: AsyncSession, row: JobRow) -> JobDetailOut:
        (card,) = await job_cards(session, [row])
        history = [
            DecisionHistoryOut(
                outcome=d.outcome,
                decided_by=d.decided_by,
                reason=d.reason,
                created_at=d.created_at,
                is_current=d.is_current,
                prompt_name=d.prompt_name,
                prompt_version=d.prompt_version,
                provider=d.provider,
                model=d.model,
            )
            for d in await DecisionsRepo(session).history(row.id)
        ]
        first_search = await session.scalar(
            select(JobSourceRow.search_run_id)
            .where(JobSourceRow.job_id == row.id, JobSourceRow.search_run_id.is_not(None))
            .order_by(JobSourceRow.seen_at)
            .limit(1)
        )
        return JobDetailOut(
            **card.model_dump(),
            description=row.description,
            city=row.city,
            country=row.country,
            skills_found=list(row.skills_found),
            years_found=row.years_found,
            canonical_url=row.canonical_url,
            injection_flags=list(row.injection_flags),
            decision_history=history,
            first_search_id=first_search,
        )

    @router.get("")
    async def list_jobs(
        list: Literal["explore", "applied"] = "explore",
        source: str | None = None,
        company_id: UUID | None = None,
        work_mode: str | None = None,
        city: str | None = None,
        sort: Literal["newest", "company"] = "newest",
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> JobCardPage:
        filters = JobFilters(
            state=list,
            source_kind=source,
            company_id=company_id,
            work_mode=work_mode,
            city=city,
            sort=sort,
        )
        async with deps.sessions() as session:
            page = await JobsRepo(session).page(
                filters, limit=limit, cursor=_decode(cursor) if cursor else None
            )
            return JobCardPage(
                items=await job_cards(session, page.items),
                next_cursor=_encode(page.next_cursor) if page.next_cursor else None,
            )

    @router.get("/{job_id}")
    async def read_job(job_id: UUID) -> JobDetailOut:
        async with deps.sessions() as session:
            return await detail(session, await load(session, job_id))

    @router.post("/{job_id}/restore")
    async def restore(job_id: UUID) -> JobDetailOut:
        async with deps.sessions() as session:
            row = await load(session, job_id)
            if row.state != JobState.skipped:
                raise ProblemError(409, "Only a skipped job can be restored.", reason="not_skipped")
            row.state = JobState.explore.value
            row.restored = True
            await session.commit()
            return await detail(session, await load(session, job_id))

    @router.post("/{job_id}/recheck", status_code=202)
    async def recheck(job_id: UUID) -> dict[str, UUID]:
        async with deps.sessions() as session:
            row = await load(session, job_id)
            current = await DecisionsRepo(session).current(job_id)
            if (
                row.state != JobState.explore
                or current is None
                or current.decided_by != RECHECKABLE
            ):
                raise ProblemError(
                    409,
                    "Only a job the AI has not checked can be checked again.",
                    reason="not_recheckable",
                )
            run = await RunsRepo(session).create(RECHECK_WORKFLOW, subject_id=job_id)
            await session.commit()
        await deps.queue.enqueue(run.id)
        return {"run_id": run.id}

    @router.delete("/{job_id}", status_code=204)
    async def delete_job(job_id: UUID) -> Response:
        async with deps.sessions() as session:
            row = await load(session, job_id, deleted_ok=True)
            try:
                transition(JobState(row.state), JobState.deleted)
            except IllegalJobTransitionError as error:
                raise ProblemError(409, str(error)) from error
            row.state = JobState.deleted.value
            await session.commit()
        return Response(status_code=204)

    return router
