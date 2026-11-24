"""Possible duplicates (contracts/rest-api.md): the person decides, nothing merges by itself
(FR-021, SC-008). Register this router before the jobs router so ``/jobs/duplicates`` is not read
as a job id."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.api.models import JobCardOut, job_cards, with_resumes
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.infra.job_ops import (
    PairDecidedError,
    PairNotFoundError,
    dismiss_pair,
    merge_pair,
)
from hiretitan.search.infra.models import JobRow, PossibleDuplicateRow

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
# the jobs a person has in front of them: Explore and the pipeline (not skipped, not deleted)
OFFERED_STATES = (JobState.explore.value, JobState.inquired.value, JobState.applied.value)
# The kept job takes the stronger pipeline state of the two (research R9): applied, then inquired.


@dataclass(frozen=True)
class SearchDuplicatesApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    clock: ClockPort


class DuplicatePairOut(BaseModel):
    id: UUID
    similarity: float
    status: str
    decided_at: datetime | None
    job_a: JobCardOut
    job_b: JobCardOut


class DuplicatePage(BaseModel):
    items: list[DuplicatePairOut]
    next_cursor: str | None = None


def create_duplicates_router(deps: SearchDuplicatesApiDeps) -> APIRouter:
    router = APIRouter(prefix="/jobs/duplicates", tags=["jobs"])

    async def render(
        session: AsyncSession, pairs: list[PossibleDuplicateRow]
    ) -> list[DuplicatePairOut]:
        ids = {j for p in pairs for j in (p.job_a_id, p.job_b_id)}
        rows = list(await session.scalars(select(JobRow).where(JobRow.id.in_(ids)))) if ids else []
        found_cards = await job_cards(session, rows)
        await with_resumes(session, found_cards)  # a pair can hold a pipeline job
        cards = {c.id: c for c in found_cards}
        return [
            DuplicatePairOut(
                id=p.id,
                similarity=float(p.similarity),
                status=p.status,
                decided_at=p.decided_at,
                job_a=cards[p.job_a_id],
                job_b=cards[p.job_b_id],
            )
            for p in pairs
        ]

    @router.get("")
    async def list_pairs(
        status: Literal["open", "merged", "dismissed"] = "open",
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> DuplicatePage:
        limit = max(1, min(limit, MAX_LIMIT))
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        async with deps.sessions() as session:
            query = select(PossibleDuplicateRow).where(PossibleDuplicateRow.status == status)
            if status == "open":
                # only pairs the person can see both jobs of: a job the rules left out, or one
                # they deleted, is not in front of them, so neither is its pair (it comes back
                # if the job is restored)
                job_a, job_b = aliased(JobRow), aliased(JobRow)
                query = (
                    query.join(job_a, job_a.id == PossibleDuplicateRow.job_a_id)
                    .join(job_b, job_b.id == PossibleDuplicateRow.job_b_id)
                    .where(job_a.state.in_(OFFERED_STATES), job_b.state.in_(OFFERED_STATES))
                )
            pairs = list(
                await session.scalars(
                    query.order_by(PossibleDuplicateRow.created_at, PossibleDuplicateRow.id)
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            return DuplicatePage(
                items=await render(session, pairs[:limit]),
                next_cursor=str(offset + limit) if len(pairs) > limit else None,
            )

    @router.post("/{pair_id}/merge")
    async def merge(pair_id: UUID) -> DuplicatePairOut:
        """Keep the older job (A) and move the other's sources onto it; the other is deleted.
        The kept job takes the stronger of the two pipeline states, with that job's date."""
        async with deps.sessions() as session:
            try:
                pair = await merge_pair(session, pair_id, deps.clock.now())
            except PairNotFoundError as error:
                raise ProblemError(404, "That pair does not exist.") from error
            except PairDecidedError as error:
                raise ProblemError(409, str(error), reason="already_decided") from error
            await session.commit()
            return (await render(session, [pair]))[0]

    @router.post("/{pair_id}/dismiss")
    async def dismiss(pair_id: UUID) -> DuplicatePairOut:
        async with deps.sessions() as session:
            try:
                pair = await dismiss_pair(session, pair_id, deps.clock.now())
            except PairNotFoundError as error:
                raise ProblemError(404, "That pair does not exist.") from error
            except PairDecidedError as error:
                raise ProblemError(409, str(error), reason="already_decided") from error
            await session.commit()
            return (await render(session, [pair]))[0]

    return router
