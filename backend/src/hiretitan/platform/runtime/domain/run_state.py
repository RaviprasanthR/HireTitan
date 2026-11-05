"""Workflow run state machine (data-model.md, ``app.workflow_runs``).

Pure: no I/O. The repository persists the result and the database repeats the
``pause_reason``/``waiting_for`` rules as CHECK constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    awaiting_review = "awaiting_review"
    paused = "paused"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class PauseReason(StrEnum):
    key_missing = "key_missing"
    key_rejected = "key_rejected"
    budget_reached = "budget_reached"


class WaitingFor(StrEnum):
    profile_review = "profile_review"
    injection_decision = "injection_decision"


ALLOWED_TRANSITIONS: Final[dict[RunStatus, frozenset[RunStatus]]] = {
    RunStatus.queued: frozenset({RunStatus.running, RunStatus.failed}),
    RunStatus.running: frozenset(
        {
            RunStatus.awaiting_review,
            RunStatus.paused,
            RunStatus.done,
            RunStatus.failed,
            RunStatus.cancelled,
        }
    ),
    RunStatus.awaiting_review: frozenset({RunStatus.queued, RunStatus.cancelled}),
    RunStatus.paused: frozenset({RunStatus.queued, RunStatus.cancelled}),
    RunStatus.failed: frozenset({RunStatus.queued}),
    RunStatus.done: frozenset(),
    RunStatus.cancelled: frozenset(),
}

FINAL_STATUSES: Final = frozenset(s for s, targets in ALLOWED_TRANSITIONS.items() if not targets)


class InvalidRunStateError(ValueError):
    """A state whose reason fields don't match its status."""


class IllegalTransitionError(ValueError):
    def __init__(self, current: RunStatus, target: RunStatus) -> None:
        super().__init__(f"Run cannot move from {current} to {target}")
        self.current = current
        self.target = target


@dataclass(frozen=True, slots=True)
class RunState:
    status: RunStatus
    pause_reason: PauseReason | None = None
    waiting_for: WaitingFor | None = None

    def __post_init__(self) -> None:
        paused = self.status is RunStatus.paused
        if paused != (self.pause_reason is not None):
            raise InvalidRunStateError("pause_reason is required iff status is paused")
        awaiting = self.status is RunStatus.awaiting_review
        if awaiting != (self.waiting_for is not None):
            raise InvalidRunStateError("waiting_for is required iff status is awaiting_review")

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES


def can_transition(current: RunStatus, target: RunStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition(
    state: RunState,
    target: RunStatus,
    *,
    pause_reason: PauseReason | None = None,
    waiting_for: WaitingFor | None = None,
) -> RunState:
    """Return the next state, or raise if the move is not allowed."""
    if not can_transition(state.status, target):
        raise IllegalTransitionError(state.status, target)
    return RunState(target, pause_reason=pause_reason, waiting_for=waiting_for)
