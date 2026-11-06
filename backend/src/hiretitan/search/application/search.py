"""Starting, stopping and writing the batches of a search (US1, FR-004, FR-008, FR-009).

``start_search`` checks that setup is complete, that rules are approved and that no other
search is active, then records the run and hands it to the queue. ``store_batch`` writes one
batch (jobs, sources, decisions, company results, counts, cost and the progress event) in a
single transaction, so a stopped or crashed search never leaves a half-written batch. The
caller announces the finished batch once it is committed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from hiretitan.search.application.rules import RuleSetView
from hiretitan.search.domain.job_state import JobState, apply_new

SearchMode = Literal["rules_and_ai", "rules_only"]


class SetupIncompleteError(Exception):
    """Setup (profile and preferences) is not finished yet."""


class SearchAlreadyRunningError(Exception):
    """Only one search runs at a time (FR-009)."""


class SearchNotRunningError(Exception):
    """There is no such search, or it already ended."""


class ApprovedRules(Protocol):
    async def require_approved(self) -> RuleSetView: ...


class SetupGate(Protocol):
    async def setup_complete(self) -> bool: ...


class RunQueue(Protocol):
    async def enqueue(self, run_id: UUID, resume: Any = None) -> None: ...


@dataclass(frozen=True, slots=True)
class StartedSearch:
    search_run_id: UUID
    run_id: UUID


@dataclass(frozen=True, slots=True)
class DecisionInput:
    outcome: Literal["shown", "skipped"]
    decided_by: Literal["rule", "ai", "person", "rules_only_fallback"]
    reason: str
    rule_key: str | None = None
    # prompt_name, prompt_version, provider, model, llm_call_id (AI decisions only)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NewJob:
    """A posting the search has not seen before, with its decision already made."""

    company_id: UUID | None
    company_name: str
    title: str
    location_text: str | None
    city: str | None
    country: str | None
    work_mode: str | None
    posted_at: datetime | None
    description: str
    skills_found: tuple[str, ...]
    years_found: Decimal | None
    canonical_url: str | None
    ats_vendor: str | None
    requisition_id: str | None
    source_url: str
    injection_flags: list[dict[str, Any]]
    decision: DecisionInput
    candidates: tuple[tuple[UUID, float], ...] = ()  # (existing job id, similarity)
    source_kind: str = "company_board"


@dataclass(frozen=True, slots=True)
class SeenJob:
    """A posting that matches a job already stored: only a new source and a fresh sighting."""

    job_id: UUID
    source_url: str
    source_kind: str = "company_board"


@dataclass(frozen=True, slots=True)
class CompanyOutcome:
    company_id: UUID
    result: str  # ok | failed | no_jobs | blocked | unreadable
    jobs_found: int
    error: str | None


@dataclass(frozen=True, slots=True)
class BatchWrite:
    search_run_id: UUID
    batch_no: int
    new: list[NewJob]
    seen: list[SeenJob]
    companies: list[CompanyOutcome]
    next_index: int
    ai_cost_delta: Decimal
    now: datetime


@dataclass(frozen=True, slots=True)
class BatchCounts:
    jobs_found: int = 0
    skipped_by_rules: int = 0
    judged_by_ai: int = 0
    kept: int = 0
    added: int = 0
    merged: int = 0
    not_checked_by_ai: int = 0
    progress: dict[str, Any] = field(default_factory=dict)  # for the progress event


class SearchTransaction(Protocol):
    """One database transaction for the search tables."""

    async def active_search_exists(self) -> bool: ...

    async def create_run(
        self, rule_set_id: UUID, mode: str, started_at: datetime
    ) -> StartedSearch: ...

    async def request_stop(self, search_run_id: UUID) -> bool:
        """Set the stop flag on a search that has not ended; False when there is none."""
        ...

    async def insert_job(self, job: NewJob, state: str, run_id: UUID, now: datetime) -> UUID: ...

    async def touch_seen(self, seen: SeenJob, run_id: UUID, now: datetime) -> None: ...

    async def record_decision(
        self, job_id: UUID, decision: DecisionInput, run_id: UUID
    ) -> None: ...

    async def add_candidate(self, job_id: UUID, other: UUID, similarity: float) -> None: ...

    async def add_company_outcome(
        self, run_id: UUID, batch_no: int, outcome: CompanyOutcome
    ) -> None: ...

    async def advance_run(
        self, run_id: UUID, counts: BatchCounts, next_index: int, ai_cost_delta: Decimal
    ) -> dict[str, Any]:
        """Add the counts and the cost, count the batch, set ``next_index``; return the
        progress numbers for the event."""
        ...

    async def commit(self) -> None: ...


async def start_search(
    mode: SearchMode,
    *,
    rules: ApprovedRules,
    setup: SetupGate,
    store: SearchTransaction,
    queue: RunQueue,
    now: datetime,
) -> StartedSearch:
    approved = await rules.require_approved()
    if not await setup.setup_complete():
        raise SetupIncompleteError
    if await store.active_search_exists():
        raise SearchAlreadyRunningError
    started = await store.create_run(approved.id, mode, now)
    await store.commit()
    await queue.enqueue(started.run_id)
    return started


async def request_stop(store: SearchTransaction, search_run_id: UUID) -> None:
    if not await store.request_stop(search_run_id):
        raise SearchNotRunningError
    await store.commit()


async def store_batch(store: SearchTransaction, write: BatchWrite) -> BatchCounts:
    """Write one batch. Either everything is stored and the event is sent, or nothing is."""
    run_id = write.search_run_id
    skipped_by_rules = judged_by_ai = kept = added = not_checked = 0
    for job in write.new:
        decision = job.decision
        state = apply_new(skipped=decision.outcome == "skipped")
        job_id = await store.insert_job(job, state.value, run_id, write.now)
        await store.record_decision(job_id, decision, run_id)
        for other, similarity in job.candidates:
            await store.add_candidate(job_id, other, similarity)
        skipped_by_rules += decision.decided_by == "rule" and decision.outcome == "skipped"
        judged_by_ai += decision.decided_by == "ai"
        not_checked += decision.decided_by == "rules_only_fallback"
        if state is JobState.explore:
            added += 1
            kept += decision.decided_by in ("ai", "rules_only_fallback")
    for seen in write.seen:
        await store.touch_seen(seen, run_id, write.now)
    for outcome in write.companies:
        await store.add_company_outcome(run_id, write.batch_no, outcome)
    counts = BatchCounts(
        jobs_found=len(write.new) + len(write.seen),
        skipped_by_rules=skipped_by_rules,
        judged_by_ai=judged_by_ai,
        kept=kept,
        added=added,
        merged=len(write.seen),
        not_checked_by_ai=not_checked,
    )
    progress = await store.advance_run(run_id, counts, write.next_index, write.ai_cost_delta)
    await store.commit()
    return replace(counts, progress={"search_run_id": str(run_id), **progress})
