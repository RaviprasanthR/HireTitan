"""The database side of a search: one transaction over the search tables (T029)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.application.alerts import KnownJob, Sighting
from hiretitan.search.application.search import (
    BatchCounts,
    CompanyOutcome,
    DecisionInput,
    NewJob,
    SearchAlreadyRunningError,
    SeenJob,
    StartedSearch,
)
from hiretitan.search.domain.dedup import DedupJob
from hiretitan.search.infra.models import (
    AlertSightingRow,
    CompanyRow,
    JobRow,
    SearchRunCompanyRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import DecisionsRepo, DuplicatesRepo, JobsRepo, SearchRunsRepo

WORKFLOW = "job_search"


class SearchStore:
    workflow_name = WORKFLOW

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._runs = SearchRunsRepo(session)
        self._jobs = JobsRepo(session)

    async def active_search_exists(self) -> bool:
        return await self._runs.active() is not None

    async def create_run(self, rule_set_id: UUID, mode: str, started_at: datetime) -> StartedSearch:
        try:
            async with self._session.begin_nested():
                workflow = await RunsRepo(self._session).create(self.workflow_name)
        except IntegrityError as error:  # the database allows one active search (FR-009)
            raise SearchAlreadyRunningError from error
        run = await self._runs.create(
            workflow_run_id=workflow.id,
            rule_set_id=rule_set_id,
            mode=mode,
            company_order=[],
            started_at=started_at,
        )
        return StartedSearch(run.id, workflow.id)

    async def request_stop(self, search_run_id: UUID) -> bool:
        run = await self._runs.get(search_run_id)
        if run is None or run.outcome is not None:
            return False
        await self._runs.request_stop(search_run_id)
        return True

    async def insert_job(self, job: NewJob, state: str, run_id: UUID, now: datetime) -> UUID:
        row = await self._jobs.add(
            company_id=job.company_id,
            company_name=job.company_name,
            title=job.title,
            role_short=job.decision.role,
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
            ats_vendor=job.ats_vendor,
            requisition_id=job.requisition_id,
            state=state,
            injection_flags=job.injection_flags,
        )
        await self._jobs.add_source(
            row.id, kind=job.source_kind, url=job.source_url, seen_at=now, search_run_id=run_id
        )
        return row.id

    async def touch_seen(self, seen: SeenJob, run_id: UUID, now: datetime) -> None:
        job = await self._jobs.get(seen.job_id)
        if job is None:
            return
        if job.state == "deleted":
            return  # a job the person deleted is left exactly as it is
        job.last_seen_at = now
        job.listed = True
        await self._session.flush()
        known = await self._session.scalar(
            text(
                "SELECT 1 FROM app.job_sources WHERE job_id = :job AND kind = :kind AND url = :url"
            ),
            {"job": seen.job_id, "kind": seen.source_kind, "url": seen.source_url},
        )
        if known is None:
            await self._jobs.add_source(
                seen.job_id,
                kind=seen.source_kind,
                url=seen.source_url,
                seen_at=now,
                search_run_id=run_id,
            )

    async def record_decision(self, job_id: UUID, decision: DecisionInput, run_id: UUID) -> None:
        await DecisionsRepo(self._session).record(
            job_id,
            outcome=decision.outcome,
            decided_by=decision.decided_by,
            reason=decision.reason,
            rule_key=decision.rule_key,
            search_run_id=run_id,
            **decision.provenance,
        )

    async def add_candidate(self, job_id: UUID, other: UUID, similarity: float) -> None:
        await DuplicatesRepo(self._session).add(job_id, other, similarity=similarity)

    async def add_company_outcome(
        self, run_id: UUID, batch_no: int, outcome: CompanyOutcome
    ) -> None:
        self._session.add(
            SearchRunCompanyRow(
                search_run_id=run_id,
                company_id=outcome.company_id,
                batch_no=batch_no,
                result=outcome.result,
                jobs_found=outcome.jobs_found,
                error=outcome.error[:300] if outcome.error else None,
            )
        )
        await self._session.flush()

    async def advance_run(
        self, run_id: UUID, counts: BatchCounts, next_index: int
    ) -> dict[str, Any]:
        await self._session.execute(
            update(SearchRunRow)
            .where(SearchRunRow.id == run_id)
            .values(
                batches_done=SearchRunRow.batches_done + 1,
                next_index=next_index,
                jobs_found=SearchRunRow.jobs_found + counts.jobs_found,
                skipped_by_rules=SearchRunRow.skipped_by_rules + counts.skipped_by_rules,
                judged_by_ai=SearchRunRow.judged_by_ai + counts.judged_by_ai,
                kept=SearchRunRow.kept + counts.kept,
                added=SearchRunRow.added + counts.added,
                merged=SearchRunRow.merged + counts.merged,
                not_checked_by_ai=SearchRunRow.not_checked_by_ai + counts.not_checked_by_ai,
            )
        )
        await self._session.flush()
        run = await self._runs.get(run_id)
        assert run is not None
        read = await self._session.scalar(
            select(func.count())
            .select_from(SearchRunCompanyRow)
            .where(SearchRunCompanyRow.search_run_id == run_id)
        )
        return {
            "batches_done": run.batches_done,
            "companies_read": read or 0,
            "added": run.added,
        }

    async def commit(self) -> None:
        await self._session.commit()


def _dedup(row: JobRow) -> DedupJob:
    return DedupJob(
        row.id,
        row.company_name,
        row.city,
        row.title,
        row.canonical_url,
        row.ats_vendor,
        row.requisition_id,
    )


class AlertSearchStore(SearchStore):
    """The search transaction for alert postings (feature 002c): the same writer as any search,
    plus the lookups deduplication needs and the sightings, written in the same commit."""

    workflow_name = "mail_check"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._inserted: dict[str, UUID] = {}  # source url -> the job this batch inserted
        self._by_url: list[tuple[str, Sighting]] = []
        self._by_job: list[tuple[UUID, Sighting]] = []

    async def insert_job(self, job: NewJob, state: str, run_id: UUID, now: datetime) -> UUID:
        job_id = await super().insert_job(job, state, run_id, now)
        self._inserted[job.source_url] = job_id
        return job_id

    async def exact_matches(
        self, canonical: str | None, vendor: str | None, requisition_id: str | None
    ) -> list[KnownJob]:
        clauses = []
        if canonical:
            clauses.append(JobRow.canonical_url == canonical)
        if vendor and requisition_id:
            clauses.append(
                and_(JobRow.ats_vendor == vendor, JobRow.requisition_id == requisition_id)
            )
        if not clauses:
            return []
        rows = await self._session.scalars(select(JobRow).where(or_(*clauses)))
        # a job that is still there comes before a deleted one, so a live match always wins
        ordered = sorted(rows, key=lambda r: (r.state == "deleted", r.created_at, r.id))
        return [KnownJob(_dedup(r), r.state) for r in ordered]

    async def jobs_of_company(self, name: str) -> list[KnownJob]:
        rows = await self._session.scalars(
            select(JobRow).where(func.lower(JobRow.company_name) == name.lower())
        )
        return [KnownJob(_dedup(r), r.state) for r in rows]

    async def company_id(self, name: str) -> UUID | None:
        """Found by name only: a company that is not listed is never created from an email."""
        return await self._session.scalar(
            select(CompanyRow.id)
            .where(func.lower(CompanyRow.name) == name.lower(), CompanyRow.deleted_at.is_(None))
            .order_by(CompanyRow.created_at, CompanyRow.id)
            .limit(1)
        )

    def queue_sighting(self, source_url: str, sighting: Sighting) -> None:
        self._by_url.append((source_url, sighting))

    def queue_sighting_for_job(self, job_id: UUID, sighting: Sighting) -> None:
        self._by_job.append((job_id, sighting))

    async def commit(self) -> None:
        pairs = [(self._inserted[url], s) for url, s in self._by_url if url in self._inserted]
        for job_id, sighting in [*pairs, *self._by_job]:
            await self._session.execute(
                pg_insert(AlertSightingRow)
                .values(
                    job_id=job_id,
                    read_message_id=sighting.read_message_id,
                    site=sighting.site,
                    link=sighting.link[:2000],
                    alert_date=sighting.alert_date,
                    posted_at=sighting.posted_at,
                )
                .on_conflict_do_nothing(constraint="uq_alert_sightings_job_id_read_message_id")
            )
        self._by_url, self._by_job = [], []
        await super().commit()
