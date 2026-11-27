"""002m T018: the job rules that used to sit in the routers now live in the use cases, so the
routes and Mikasa's actions share one path (research R3; 002 FR-036, FR-037; 002d FR-005 to
FR-008; 002 recheck and restore rules)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4

import pytest

from hiretitan.search.application.job_rules import check_recheckable, restore_skipped
from hiretitan.search.application.pipeline import (
    PipelineRuleError,
    mark_applied,
    mark_inquired,
    undo_applied,
    undo_inquired,
)
from hiretitan.search.domain.job_state import JobState

TODAY = date(2026, 11, 24)


@dataclass
class Store:
    states: dict[UUID, JobState] = field(default_factory=dict)
    restored: set[UUID] = field(default_factory=set)

    async def state_of(self, job_id: UUID) -> JobState | None:
        return self.states.get(job_id)

    async def set_status(
        self,
        job_id: UUID,
        state: JobState,
        applied_on: date | None,
        inquired_on: date | None = None,
    ) -> None:
        self.states[job_id] = state

    async def mark_restored(self, job_id: UUID) -> None:
        self.states[job_id] = JobState.explore
        self.restored.add(job_id)


def job(store: Store, state: JobState) -> UUID:
    job_id = uuid4()
    store.states[job_id] = state
    return job_id


async def refused(reason: str, call: object) -> None:
    with pytest.raises(PipelineRuleError) as caught:
        await call  # type: ignore[misc]
    assert caught.value.reason == reason
    assert str(caught.value)


async def test_FR036_already_applied_is_a_rule() -> None:
    store = Store()
    applied = job(store, JobState.applied)
    await refused("already_applied", mark_applied(store, applied, today=TODAY))


async def test_FR036_undo_needs_an_applied_job() -> None:
    store = Store()
    explore = job(store, JobState.explore)
    await refused("not_applied", undo_applied(store, explore))


async def test_FR037_inquire_rules() -> None:
    store = Store()
    inquired = job(store, JobState.inquired)
    applied = job(store, JobState.applied)
    explore = job(store, JobState.explore)
    await refused("already_inquired", mark_inquired(store, inquired, today=TODAY))
    await refused("already_applied", mark_inquired(store, applied, today=TODAY))
    await refused("not_inquired", undo_inquired(store, explore))


async def test_FR036_valid_marks_still_work() -> None:
    store = Store()
    explore = job(store, JobState.explore)
    await mark_applied(store, explore, today=TODAY)
    assert store.states[explore] is JobState.applied
    await undo_applied(store, explore)
    assert store.states[explore] is JobState.explore


async def test_restore_only_a_skipped_job() -> None:
    store = Store()
    skipped = job(store, JobState.skipped)
    explore = job(store, JobState.explore)

    await restore_skipped(store, skipped)

    assert store.states[skipped] is JobState.explore
    assert skipped in store.restored
    await refused("not_skipped", restore_skipped(store, explore))


def test_recheck_only_a_job_the_ai_has_not_checked() -> None:
    check_recheckable(JobState.explore, "rules_only_fallback")
    for state, decided_by in (
        (JobState.applied, "rules_only_fallback"),
        (JobState.explore, "ai"),
        (JobState.explore, None),
    ):
        with pytest.raises(PipelineRuleError) as caught:
            check_recheckable(state, decided_by)
        assert caught.value.reason == "not_recheckable"
