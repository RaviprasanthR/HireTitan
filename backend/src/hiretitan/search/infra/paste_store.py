"""The database side of adding a job by hand (T045). Nothing here commits."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.application.paste import SOURCE_KIND
from hiretitan.search.application.search import DecisionInput, NewJob
from hiretitan.search.domain.dedup import DedupJob
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.infra.models import CompanyRow, JobRow, JobSourceRow
from hiretitan.search.infra.repos import DecisionsRepo, DuplicatesRepo, JobsRepo


class SqlPasteStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._jobs = JobsRepo(session)

    async def find_by_url(self, canonical: str) -> tuple[UUID, JobState] | None:
        row = (
            await self._session.execute(
                select(JobRow.id, JobRow.state).where(JobRow.canonical_url == canonical)
            )
        ).first()
        return None if row is None else (row.id, JobState(row.state))

    async def company_id(self, name: str) -> UUID | None:
        return await self._session.scalar(
            select(CompanyRow.id)
            .where(func.lower(CompanyRow.name) == name.lower(), CompanyRow.deleted_at.is_(None))
            .limit(1)
        )

    async def jobs_of_company(self, name: str) -> list[DedupJob]:
        rows = await self._session.scalars(
            select(JobRow).where(
                func.lower(JobRow.company_name) == name.lower(), JobRow.state != "deleted"
            )
        )
        return [
            DedupJob(
                r.id,
                r.company_name,
                r.city,
                r.title,
                r.canonical_url,
                r.ats_vendor,
                r.requisition_id,
            )
            for r in rows
        ]

    async def insert(self, job: NewJob, now: datetime) -> UUID:
        row = await self._jobs.add(
            company_id=job.company_id,
            company_name=job.company_name,
            title=job.title,
            location_text=job.location_text,
            city=job.city,
            country=job.country,
            work_mode=job.work_mode,
            posted_at=job.posted_at,
            first_seen_at=now,
            last_seen_at=now,
            description=job.description,
            skills_found=list(job.skills_found),
            years_found=job.years_found,
            canonical_url=job.canonical_url,
            state=JobState.explore.value,
            injection_flags=job.injection_flags,
        )
        await self._jobs.add_source(row.id, kind=job.source_kind, url=job.source_url, seen_at=now)
        await self._record(row.id, job.decision)
        return row.id

    async def add_source(self, job_id: UUID, url: str, now: datetime) -> None:
        known = await self._session.scalar(
            select(JobSourceRow.id).where(JobSourceRow.job_id == job_id, JobSourceRow.url == url)
        )
        if known is None:
            await self._jobs.add_source(job_id, kind=SOURCE_KIND, url=url, seen_at=now)

    async def bring_back(self, job_id: UUID, decision: DecisionInput) -> None:
        job = await self._jobs.get(job_id)
        assert job is not None
        job.state = JobState.explore.value
        job.restored = True
        await self._record(job_id, decision)

    async def add_candidate(self, job_id: UUID, other: UUID, similarity: float) -> None:
        await DuplicatesRepo(self._session).add(job_id, other, similarity=similarity)

    async def _record(self, job_id: UUID, decision: DecisionInput) -> None:
        await DecisionsRepo(self._session).record(
            job_id,
            outcome=decision.outcome,
            decided_by=decision.decided_by,
            reason=decision.reason,
            rule_key=decision.rule_key,
            **decision.provenance,
        )
