"""Deleting a job and deciding a possible-duplicate pair: the work the job and duplicates routes
did in place, moved here in 002m so the routes and Mikasa's actions share one path (FR-006).
Nothing here commits; the caller does."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.domain.job_state import JobState, transition
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import JobRow, JobSourceRow, PossibleDuplicateRow

STRENGTH: Final = {JobState.applied.value: 2, JobState.inquired.value: 1}

JobCleanup = Callable[[AsyncSession, UUID], Awaitable[None]]


class JobGoneError(LookupError):
    """No such job (or it was deleted already)."""


class PairNotFoundError(LookupError):
    pass


class PairDecidedError(ValueError):
    pass


async def delete_job(
    session: AsyncSession, job_id: UUID, cleanups: Sequence[JobCleanup] = ()
) -> None:
    """Soft-delete the job with everything recorded about it (002e FR-011, 002k FR-009).

    Raises ``JobGoneError`` for a missing job and ``IllegalJobTransitionError`` when its state
    cannot become deleted."""
    await InterviewsRepo(session).lock_job(job_id)  # a contact save cannot slip in after
    row = await session.get(JobRow, job_id, populate_existing=True)
    if row is None:
        raise JobGoneError(str(job_id))
    transition(JobState(row.state), JobState.deleted)
    # The date of the old state goes with it (the table requires it).
    row.state = JobState.deleted.value
    row.applied_on = None
    row.inquired_on = None
    await InterviewsRepo(session).delete_for_job(job_id)
    for cleanup in cleanups:
        await cleanup(session, job_id)
    await session.flush()


async def open_pair(session: AsyncSession, pair_id: UUID) -> PossibleDuplicateRow:
    pair = await session.get(PossibleDuplicateRow, pair_id, populate_existing=True)
    if pair is None:
        raise PairNotFoundError(str(pair_id))
    if pair.status != "open":
        raise PairDecidedError("That pair was already decided.")
    return pair


async def merge_pair(session: AsyncSession, pair_id: UUID, now: datetime) -> PossibleDuplicateRow:
    """Keep the older job (A) and move the other's sources onto it; the other is deleted.
    The kept job takes the stronger of the two pipeline states, with that job's date."""
    pair = await open_pair(session, pair_id)
    keep, loser = pair.job_a_id, pair.job_b_id
    # one lock order for both jobs, taken before anything is changed, so two merges that
    # share a job cannot wait on each other
    for job_id in sorted((keep, loser)):
        await InterviewsRepo(session).lock_job(job_id)
    have = set(await session.scalars(select(JobSourceRow.url).where(JobSourceRow.job_id == keep)))
    sources = await session.scalars(select(JobSourceRow).where(JobSourceRow.job_id == loser))
    for source in list(sources):
        if source.url not in have:
            source.job_id = keep
        # a source the kept job already has goes away with the other job's row
    loser_row = await session.get(JobRow, loser)
    keep_row = await session.get(JobRow, keep)
    assert loser_row is not None
    assert keep_row is not None
    if STRENGTH.get(loser_row.state, 0) > STRENGTH.get(keep_row.state, 0):
        keep_row.state = loser_row.state
        keep_row.applied_on = loser_row.applied_on
        keep_row.inquired_on = loser_row.inquired_on
    # a deleted job carries no date (the table allows one only on applied or inquired)
    loser_row.state = JobState.deleted.value
    loser_row.applied_on = None
    loser_row.inquired_on = None
    await InterviewsRepo(session).merge_details(keep, loser)
    pair.status = "merged"
    pair.decided_at = now
    await session.flush()
    return pair


async def dismiss_pair(session: AsyncSession, pair_id: UUID, now: datetime) -> PossibleDuplicateRow:
    pair = await open_pair(session, pair_id)
    pair.status = "dismissed"
    pair.decided_at = now
    await session.flush()
    return pair
