"""The life of a job in the person's lists (data-model.md, "State transitions").

Pure: no I/O. ``explore`` is the list the person reads, ``applied`` is what they have applied to,
``skipped`` is what the rules or the AI left out (restorable), ``deleted`` is a tombstone so a later
search does not add the job again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final


class JobState(StrEnum):
    explore = "explore"
    skipped = "skipped"
    applied = "applied"
    deleted = "deleted"


ALLOWED: Final[dict[JobState, frozenset[JobState]]] = {
    # skipped -> applied: the person found the job themselves and applied to it
    JobState.skipped: frozenset({JobState.explore, JobState.applied, JobState.deleted}),
    # explore -> skipped: a later check by the AI finds the job not relevant after all
    JobState.explore: frozenset({JobState.applied, JobState.skipped, JobState.deleted}),
    JobState.applied: frozenset({JobState.explore, JobState.deleted}),
    JobState.deleted: frozenset(),
}


class IllegalJobTransitionError(ValueError):
    def __init__(self, current: JobState, target: JobState, reason: str | None = None) -> None:
        super().__init__(reason or f"A {current} job cannot become {target}")
        self.current = current
        self.target = target


@dataclass(frozen=True, slots=True)
class JobStatus:
    state: JobState
    restored: bool = False
    applied_on: date | None = None


def apply_new(*, skipped: bool) -> JobState:
    """Where a job found for the first time lands, from the rules and the relevance check."""
    return JobState.skipped if skipped else JobState.explore


def apply_found_again(state: JobState) -> JobState:
    """A job a later search finds again keeps its state and its decision."""
    return state


def transition(current: JobState, target: JobState, *, applied_on: date | None = None) -> JobStatus:
    if target not in ALLOWED[current]:
        raise IllegalJobTransitionError(current, target)
    if target is JobState.applied:
        if applied_on is None:
            raise IllegalJobTransitionError(current, target, "Say when you applied.")
        return JobStatus(target, applied_on=applied_on)
    # skipped -> explore is the person restoring the job; later searches keep it in Explore
    return JobStatus(target, restored=current is JobState.skipped and target is JobState.explore)
