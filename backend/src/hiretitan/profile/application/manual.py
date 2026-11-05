"""Typing the profile in by hand as an autosaved review (FR-019, FR-041).

"Type it in myself" starts a resume-less run of the same workflow. It ends in an empty,
open review that autosaves like an extracted one. If a resume is still being read or is
paused, the caller may cancel that import first; one that is actively running is left alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from hiretitan.profile.application.ingest import JobQueue, OpenReviewError


class ActiveRunError(Exception):
    """A resume import is still in progress; cancelling it needs the user's go-ahead."""

    def __init__(self, active_run_id: UUID) -> None:
        super().__init__("A resume is still being read")
        self.active_run_id = active_run_id


class ReadingInProgressError(Exception):
    """The import is running right now and cannot be cancelled safely."""

    def __init__(self, active_run_id: UUID) -> None:
        super().__init__("Your resume is being read right now. Try again in a moment.")
        self.active_run_id = active_run_id


@dataclass(frozen=True, slots=True)
class ActiveRun:
    id: UUID
    running: bool  # actively executing on a worker


class ManualStore(Protocol):
    """One database transaction."""

    async def open_review_id(self) -> UUID | None: ...

    async def active_runs(self) -> list[ActiveRun]: ...

    async def cancel_run(self, run_id: UUID) -> None: ...

    async def start_manual_run(self) -> UUID: ...

    async def commit(self) -> None: ...


async def start_manual_review(
    store: ManualStore, queue: JobQueue, *, cancel_active_run: bool = False
) -> UUID:
    """Queue the run that opens an empty review; returns its id."""
    open_id = await store.open_review_id()
    if open_id is not None:
        raise OpenReviewError(open_id)
    active = await store.active_runs()
    if active:
        newest = active[-1]
        if not cancel_active_run:
            raise ActiveRunError(newest.id)
        if any(run.running for run in active):
            raise ReadingInProgressError(newest.id)
        for run in active:
            await store.cancel_run(run.id)
    run_id = await store.start_manual_run()
    await store.commit()
    await queue.enqueue(run_id)
    return run_id
