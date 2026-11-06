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

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.api.models import JobCardOut, job_cards
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.infra.models import JobRow, JobSourceRow, PossibleDuplicateRow

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


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
        cards = {c.id: c for c in await job_cards(session, rows)}
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

    async def open_pair(session: AsyncSession, pair_id: UUID) -> PossibleDuplicateRow:
        pair = await session.get(PossibleDuplicateRow, pair_id)
        if pair is None:
            raise ProblemError(404, "That pair does not exist.")
        if pair.status != "open":
            raise ProblemError(409, "That pair was already decided.", reason="already_decided")
        return pair

    @router.get("")
    async def list_pairs(
        status: Literal["open", "merged", "dismissed"] = "open",
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> DuplicatePage:
        limit = max(1, min(limit, MAX_LIMIT))
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        async with deps.sessions() as session:
            pairs = list(
                await session.scalars(
                    select(PossibleDuplicateRow)
                    .where(PossibleDuplicateRow.status == status)
                    .order_by(PossibleDuplicateRow.created_at, PossibleDuplicateRow.id)
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
        """Keep the older job (A) and move the other's sources onto it; the other is deleted."""
        async with deps.sessions() as session:
            pair = await open_pair(session, pair_id)
            keep, loser = pair.job_a_id, pair.job_b_id
            have = set(
                await session.scalars(select(JobSourceRow.url).where(JobSourceRow.job_id == keep))
            )
            sources = await session.scalars(
                select(JobSourceRow).where(JobSourceRow.job_id == loser)
            )
            for source in list(sources):
                if source.url in have:
                    await session.delete(source)
                else:
                    source.job_id = keep
            loser_row = await session.get(JobRow, loser)
            assert loser_row is not None
            loser_row.state = JobState.deleted.value
            pair.status = "merged"
            pair.decided_at = deps.clock.now()
            await session.commit()
            return (await render(session, [pair]))[0]

    @router.post("/{pair_id}/dismiss")
    async def dismiss(pair_id: UUID) -> DuplicatePairOut:
        async with deps.sessions() as session:
            pair = await open_pair(session, pair_id)
            pair.status = "dismissed"
            pair.decided_at = deps.clock.now()
            await session.commit()
            return (await render(session, [pair]))[0]

    return router
