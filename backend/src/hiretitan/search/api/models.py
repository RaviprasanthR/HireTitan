"""Response shapes shared by the search endpoints: the job card and its decision and sources."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.domain.role import short_role
from hiretitan.search.infra.models import JobRow, JobSourceRow, RelevanceDecisionRow


class SourceOut(BaseModel):
    kind: str
    url: str


class DecisionOut(BaseModel):
    outcome: str
    decided_by: str
    reason: str


class JobCardOut(BaseModel):
    id: UUID
    title: str
    role: str  # short role: the AI's when it gave one, else the title cut down by rules
    company_name: str
    location_text: str | None
    work_mode: str | None
    posted_at: datetime | None
    first_seen_at: datetime
    state: str
    restored: bool
    sources: list[SourceOut]
    decision: DecisionOut | None
    listed: bool
    applied_on: date | None


class JobCardPage(BaseModel):
    items: list[JobCardOut]
    next_cursor: str | None = None


async def job_cards(session: AsyncSession, rows: Sequence[JobRow]) -> list[JobCardOut]:
    """Cards for the rows, with their sources and current decision in two queries."""
    ids = [row.id for row in rows]
    sources: dict[UUID, list[SourceOut]] = {}
    decisions: dict[UUID, DecisionOut] = {}
    if ids:
        found = await session.scalars(
            select(JobSourceRow).where(JobSourceRow.job_id.in_(ids)).order_by(JobSourceRow.seen_at)
        )
        for source in found:
            sources.setdefault(source.job_id, []).append(
                SourceOut(kind=source.kind, url=source.url)
            )
        current = await session.scalars(
            select(RelevanceDecisionRow).where(
                RelevanceDecisionRow.job_id.in_(ids), RelevanceDecisionRow.is_current
            )
        )
        for decision in current:
            decisions[decision.job_id] = DecisionOut(
                outcome=decision.outcome, decided_by=decision.decided_by, reason=decision.reason
            )
    return [
        JobCardOut(
            id=row.id,
            title=row.title,
            role=row.role_short or short_role(row.title),
            company_name=row.company_name,
            location_text=row.location_text,
            work_mode=row.work_mode,
            posted_at=row.posted_at,
            first_seen_at=row.first_seen_at,
            state=row.state,
            restored=row.restored,
            sources=sources.get(row.id, []),
            decision=decisions.get(row.id),
            listed=row.listed,
            applied_on=row.applied_on,
        )
        for row in rows
    ]
