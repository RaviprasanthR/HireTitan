"""Marking a job applied, and undoing it (FR-036, FR-037).

An applied job leaves Explore. Later searches meet it as an exact match (the same posting seen
again), so they keep its state and never judge, skip or list it a second time.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from hiretitan.search.domain.job_state import JobState, JobStatus, transition

MAX_AGE_YEARS = 2


class JobNotFoundError(LookupError):
    """There is no such job."""


class AppliedDateError(ValueError):
    """The date is in the future or more than two years ago."""


def _two_years_before(today: date) -> date:
    try:
        return today.replace(year=today.year - MAX_AGE_YEARS)
    except ValueError:  # 29 February
        return today.replace(year=today.year - MAX_AGE_YEARS, day=28)


def check_applied_date(applied_on: date, today: date) -> None:
    if applied_on > today:
        raise AppliedDateError("The date cannot be in the future.")
    if applied_on < _two_years_before(today):
        raise AppliedDateError("The date cannot be more than 2 years ago.")


class JobStatusStore(Protocol):
    async def state_of(self, job_id: UUID) -> JobState | None: ...

    async def set_status(self, job_id: UUID, state: JobState, applied_on: date | None) -> None: ...


async def _current(store: JobStatusStore, job_id: UUID) -> JobState:
    state = await store.state_of(job_id)
    if state is None:
        raise JobNotFoundError(str(job_id))
    return state


async def mark_applied(
    store: JobStatusStore, job_id: UUID, *, today: date, applied_on: date | None = None
) -> JobStatus:
    """From Explore or from skipped (the person found it themselves). Does not commit."""
    current = await _current(store, job_id)
    chosen = applied_on or today
    check_applied_date(chosen, today)
    status = transition(current, JobState.applied, applied_on=chosen)
    await store.set_status(job_id, status.state, status.applied_on)
    return status


async def undo_applied(store: JobStatusStore, job_id: UUID) -> JobStatus:
    """Back to Explore. Does not commit."""
    status = transition(await _current(store, job_id), JobState.explore)
    await store.set_status(job_id, status.state, None)
    return status
