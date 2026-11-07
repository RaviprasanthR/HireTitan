"""Repositories for the search tables (data-model.md).

They return the ORM rows. Callers in the application layer map them to API shapes. Every method
flushes but never commits: the caller owns the transaction, so a batch can write jobs, decisions
and counts atomically (FR-008).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.infra.models import WorkflowRunRow
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.domain.vendors import ENABLED_VENDORS
from hiretitan.search.infra.models import (
    CompanyRow,
    JobRow,
    JobSourceRow,
    PossibleDuplicateRow,
    RelevanceDecisionRow,
    SearchRuleSetRow,
    SearchRunRow,
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
ACTIVE_RUN_STATUSES = ("queued", "running", "paused")


# --- companies -------------------------------------------------------------------------------


def readable_clause() -> ColumnElement[bool]:
    """A company a search can read: not hidden, not deleted, and either an enabled job-board
    provider or a careers page."""
    return and_(
        CompanyRow.hidden.is_(False),
        CompanyRow.deleted_at.is_(None),
        or_(CompanyRow.ats_vendor.in_(ENABLED_VENDORS), CompanyRow.resolution == "careers_page"),
    )


def check_manually_clause() -> ColumnElement[bool]:
    """Companies the person has to look at themselves."""
    return and_(
        CompanyRow.deleted_at.is_(None),
        or_(
            CompanyRow.resolution == "check_manually",
            CompanyRow.last_check_result.in_(("blocked", "unreadable")),
        ),
    )


class CompaniesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, **fields: Any) -> CompanyRow:
        row = CompanyRow(**fields)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, company_id: UUID) -> CompanyRow | None:
        return await self._session.get(CompanyRow, company_id)

    async def get_by_key(self, key: str) -> CompanyRow | None:
        result = await self._session.execute(select(CompanyRow).where(CompanyRow.key == key))
        return result.scalar_one_or_none()

    async def set_fields(self, company_id: UUID, **fields: Any) -> None:
        await self._session.execute(
            update(CompanyRow).where(CompanyRow.id == company_id).values(**fields)
        )
        await self._session.flush()
        await self._session.refresh(await self._session.get_one(CompanyRow, company_id))

    async def list_all(self) -> list[CompanyRow]:
        result = await self._session.execute(
            select(CompanyRow)
            .where(CompanyRow.deleted_at.is_(None))
            .order_by(func.lower(CompanyRow.name), CompanyRow.id)
        )
        return list(result.scalars())

    async def list_filtered(self, filter: str) -> list[CompanyRow]:
        """``all`` (hidden ones too), ``hidden`` or ``check_manually``; deleted rows never."""
        if filter == "check_manually":
            return await self.list_check_manually()
        if filter == "hidden":
            result = await self._session.execute(
                select(CompanyRow)
                .where(CompanyRow.deleted_at.is_(None), CompanyRow.hidden.is_(True))
                .order_by(func.lower(CompanyRow.name), CompanyRow.id)
            )
            return list(result.scalars())
        return await self.list_all()

    async def remove(self, company_id: UUID) -> None:
        await self._session.execute(delete(CompanyRow).where(CompanyRow.id == company_id))
        await self._session.flush()

    async def list_readable(self) -> list[CompanyRow]:
        result = await self._session.execute(
            select(CompanyRow)
            .where(readable_clause())
            .order_by(func.lower(CompanyRow.name), CompanyRow.id)
        )
        return list(result.scalars())

    async def list_check_manually(self) -> list[CompanyRow]:
        result = await self._session.execute(
            select(CompanyRow)
            .where(check_manually_clause())
            .order_by(func.lower(CompanyRow.name), CompanyRow.id)
        )
        return list(result.scalars())


# --- rule sets -------------------------------------------------------------------------------


class RuleSetsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, rule_set_id: UUID) -> SearchRuleSetRow | None:
        row = await self._session.get(SearchRuleSetRow, rule_set_id)
        if row is not None:
            await self._session.refresh(row)
        return row

    async def _one(self, status: str) -> SearchRuleSetRow | None:
        result = await self._session.execute(
            select(SearchRuleSetRow).where(SearchRuleSetRow.status == status)
        )
        return result.scalar_one_or_none()

    async def approved(self) -> SearchRuleSetRow | None:
        return await self._one("approved")

    async def proposed(self) -> SearchRuleSetRow | None:
        return await self._one("proposed")

    async def propose(self, rules: dict[str, Any], based_on: dict[str, Any]) -> SearchRuleSetRow:
        """A new proposal replaces the open one. The approved set is never touched."""
        await self.discard_proposed()
        latest = await self._session.scalar(select(func.max(SearchRuleSetRow.version)))
        row = SearchRuleSetRow(
            version=(latest or 0) + 1, status="proposed", rules=rules, based_on=based_on
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def update_proposed(self, rules: dict[str, Any]) -> SearchRuleSetRow | None:
        row = await self.proposed()
        if row is not None:
            row.rules = rules
            await self._session.flush()
            await self._session.refresh(row)
        return row

    async def approve(self, rule_set_id: UUID, *, now: datetime | None = None) -> SearchRuleSetRow:
        """The previous approved set becomes ``superseded`` in the same transaction."""
        await self._session.execute(
            update(SearchRuleSetRow)
            .where(SearchRuleSetRow.status == "approved")
            .values(status="superseded")
        )
        await self._session.execute(
            update(SearchRuleSetRow)
            .where(SearchRuleSetRow.id == rule_set_id)
            .values(status="approved", approved_at=now or func.now())
        )
        await self._session.flush()
        row = await self._session.get_one(SearchRuleSetRow, rule_set_id)
        await self._session.refresh(row)
        return row

    async def discard_proposed(self) -> None:
        await self._session.execute(
            delete(SearchRuleSetRow).where(SearchRuleSetRow.status == "proposed")
        )
        await self._session.flush()


# --- search runs -----------------------------------------------------------------------------


class SearchRunsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workflow_run_id: UUID,
        rule_set_id: UUID,
        mode: str,
        company_order: list[UUID],
        started_at: datetime | None = None,
    ) -> SearchRunRow:
        row = SearchRunRow(
            workflow_run_id=workflow_run_id,
            rule_set_id=rule_set_id,
            mode=mode,
            company_order=company_order,
            started_at=started_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, search_run_id: UUID) -> SearchRunRow | None:
        row = await self._session.get(SearchRunRow, search_run_id)
        if row is not None:
            await self._session.refresh(row)
        return row

    async def by_workflow_run(self, workflow_run_id: UUID) -> SearchRunRow | None:
        result = await self._session.execute(
            select(SearchRunRow).where(SearchRunRow.workflow_run_id == workflow_run_id)
        )
        return result.scalar_one_or_none()

    async def previous(self, search_run: SearchRunRow) -> SearchRunRow | None:
        """The search before this one, if any."""
        result = await self._session.execute(
            select(SearchRunRow)
            .where(
                SearchRunRow.id != search_run.id,
                SearchRunRow.created_at <= search_run.created_at,
            )
            .order_by(SearchRunRow.created_at.desc(), SearchRunRow.id.desc())
        )
        return result.scalars().first()

    async def set_company_order(self, search_run_id: UUID, order: list[UUID]) -> None:
        await self._session.execute(
            update(SearchRunRow).where(SearchRunRow.id == search_run_id).values(company_order=order)
        )
        await self._session.flush()

    async def active(self) -> SearchRunRow | None:
        """The search that is queued, running or paused (FR-009), if any."""
        result = await self._session.execute(
            select(SearchRunRow)
            .join(WorkflowRunRow, WorkflowRunRow.id == SearchRunRow.workflow_run_id)
            .where(WorkflowRunRow.status.in_(ACTIVE_RUN_STATUSES))
        )
        return result.scalar_one_or_none()

    async def latest(self) -> SearchRunRow | None:
        result = await self._session.execute(
            select(SearchRunRow).order_by(SearchRunRow.created_at.desc(), SearchRunRow.id.desc())
        )
        return result.scalars().first()

    async def request_stop(self, search_run_id: UUID) -> None:
        await self._session.execute(
            update(SearchRunRow).where(SearchRunRow.id == search_run_id).values(stop_requested=True)
        )
        await self._session.flush()

    async def finish(
        self,
        search_run_id: UUID,
        *,
        outcome: str,
        finished_at: datetime,
        stop_message: str | None = None,
    ) -> None:
        await self._session.execute(
            update(SearchRunRow)
            .where(SearchRunRow.id == search_run_id)
            .values(outcome=outcome, stop_message=stop_message, finished_at=finished_at)
        )
        await self._session.flush()


# --- jobs ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JobFilters:
    state: str
    source_kind: str | None = None
    company_id: UUID | None = None
    work_mode: str | None = None
    city: str | None = None
    sort: Literal["newest", "company"] = "newest"


@dataclass(frozen=True, slots=True)
class Cursor:
    """Where the next page starts: the last row's sort value and id."""

    sort_value: datetime | str
    id: UUID


@dataclass(frozen=True, slots=True)
class Page:
    items: list[JobRow]
    next_cursor: Cursor | None


class JobsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, **fields: Any) -> JobRow:
        row = JobRow(**fields)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, job_id: UUID) -> JobRow | None:
        row = await self._session.get(JobRow, job_id)
        if row is not None:
            await self._session.refresh(row)
        return row

    async def set_state(self, job_id: UUID, state: str) -> None:
        await self._session.execute(update(JobRow).where(JobRow.id == job_id).values(state=state))
        await self._session.flush()

    async def state_of(self, job_id: UUID) -> JobState | None:
        value = await self._session.scalar(select(JobRow.state).where(JobRow.id == job_id))
        return JobState(value) if value is not None else None

    async def set_status(self, job_id: UUID, state: JobState, applied_on: date | None) -> None:
        """State and applied date change together (the table requires it)."""
        await self._session.execute(
            update(JobRow)
            .where(JobRow.id == job_id)
            .values(state=state.value, applied_on=applied_on)
        )
        await self._session.flush()

    async def add_source(
        self,
        job_id: UUID,
        *,
        kind: str,
        url: str,
        seen_at: datetime,
        search_run_id: UUID | None = None,
    ) -> None:
        self._session.add(
            JobSourceRow(
                job_id=job_id, kind=kind, url=url, seen_at=seen_at, search_run_id=search_run_id
            )
        )
        await self._session.flush()

    async def page(
        self, filters: JobFilters, *, limit: int = DEFAULT_PAGE_SIZE, cursor: Cursor | None = None
    ) -> Page:
        """Keyset paging, so rows added while the person scrolls never shift a page (SC-010)."""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        by_company = filters.sort == "company"
        by_applied = filters.state == "applied"  # the Applied list is newest application first
        key: Any = (
            func.lower(JobRow.company_name)
            if by_company
            else JobRow.applied_on
            if by_applied
            else JobRow.sort_key
        )
        query = select(JobRow).where(JobRow.state == filters.state)
        if filters.company_id is not None:
            query = query.where(JobRow.company_id == filters.company_id)
        if filters.work_mode is not None:
            query = query.where(JobRow.work_mode == filters.work_mode)
        if filters.city is not None:
            query = query.where(func.lower(JobRow.city) == filters.city.lower())
        if filters.source_kind is not None:
            query = query.where(
                exists().where(
                    JobSourceRow.job_id == JobRow.id, JobSourceRow.kind == filters.source_kind
                )
            )
        if cursor is not None:
            value: Any = cursor.sort_value
            if by_applied and not by_company and isinstance(value, str):
                value = date.fromisoformat(value)
            if by_company:
                after = or_(key > value, and_(key == value, JobRow.id > cursor.id))
            else:
                after = or_(key < value, and_(key == value, JobRow.id > cursor.id))
            query = query.where(after)
        order = (key.asc() if by_company else key.desc(), JobRow.id.asc())
        result = await self._session.execute(query.order_by(*order).limit(limit + 1))
        rows = list(result.scalars())
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            token: datetime | str
            if by_company:
                token = last.company_name.lower()
            elif by_applied and last.applied_on is not None:
                token = last.applied_on.isoformat()
            else:
                token = last.sort_key
            next_cursor = Cursor(token, last.id)
        return Page(items, next_cursor)


# --- relevance decisions ---------------------------------------------------------------------


class DecisionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        job_id: UUID,
        *,
        outcome: str,
        decided_by: str,
        reason: str,
        supersede: bool = True,
        **provenance: Any,
    ) -> RelevanceDecisionRow:
        """Add a decision and make it the current one. History is kept. ``supersede=False`` skips
        clearing the old current flag (only to prove the database refuses two)."""
        if supersede:
            await self._session.execute(
                update(RelevanceDecisionRow)
                .where(RelevanceDecisionRow.job_id == job_id, RelevanceDecisionRow.is_current)
                .values(is_current=False)
            )
        row = RelevanceDecisionRow(
            job_id=job_id,
            outcome=outcome,
            decided_by=decided_by,
            reason=reason,
            is_current=True,
            **provenance,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def current(self, job_id: UUID) -> RelevanceDecisionRow | None:
        result = await self._session.execute(
            select(RelevanceDecisionRow).where(
                RelevanceDecisionRow.job_id == job_id, RelevanceDecisionRow.is_current
            )
        )
        return result.scalar_one_or_none()

    async def history(self, job_id: UUID) -> list[RelevanceDecisionRow]:
        result = await self._session.execute(
            select(RelevanceDecisionRow)
            .where(RelevanceDecisionRow.job_id == job_id)
            .order_by(RelevanceDecisionRow.created_at, RelevanceDecisionRow.id)
        )
        return list(result.scalars())


# --- possible duplicates ---------------------------------------------------------------------


class DuplicatesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job_one: UUID, job_two: UUID, *, similarity: float) -> None:
        """Store the pair in id order; a pair already known is left as it is."""
        first, second = sorted((job_one, job_two))
        known = await self._session.scalar(
            select(PossibleDuplicateRow.id).where(
                PossibleDuplicateRow.job_a_id == first, PossibleDuplicateRow.job_b_id == second
            )
        )
        if known is None:
            self._session.add(
                PossibleDuplicateRow(job_a_id=first, job_b_id=second, similarity=similarity)
            )
            await self._session.flush()

    async def list_open(self) -> list[PossibleDuplicateRow]:
        result = await self._session.execute(
            select(PossibleDuplicateRow)
            .where(PossibleDuplicateRow.status == "open")
            .order_by(PossibleDuplicateRow.created_at, PossibleDuplicateRow.id)
        )
        return list(result.scalars())

    async def set_status(self, pair_id: UUID, status: str, *, decided_at: datetime) -> None:
        await self._session.execute(
            update(PossibleDuplicateRow)
            .where(PossibleDuplicateRow.id == pair_id)
            .values(status=status, decided_at=decided_at)
        )
        await self._session.flush()
