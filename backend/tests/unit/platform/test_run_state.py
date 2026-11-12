"""T012: the workflow run state machine (data-model.md, "State transitions")."""

from __future__ import annotations

import itertools

import pytest

from hiretitan.platform.runtime.domain.run_state import (
    ALLOWED_TRANSITIONS,
    FINAL_STATUSES,
    IllegalTransitionError,
    InvalidRunStateError,
    PauseReason,
    RunState,
    RunStatus,
    WaitingFor,
    transition,
)

S = RunStatus

QUEUED = RunState(S.queued)
RUNNING = RunState(S.running)
AWAITING = RunState(S.awaiting_review, waiting_for=WaitingFor.profile_review)
PAUSED = RunState(S.paused, pause_reason=PauseReason.key_missing)
FAILED = RunState(S.failed)


def test_queued_to_running() -> None:
    assert transition(QUEUED, S.running) == RUNNING


def test_running_to_awaiting_review() -> None:
    new = transition(RUNNING, S.awaiting_review, waiting_for=WaitingFor.injection_decision)
    assert new == RunState(S.awaiting_review, waiting_for=WaitingFor.injection_decision)


def test_running_to_paused() -> None:
    new = transition(RUNNING, S.paused, pause_reason=PauseReason.key_missing)
    assert new == RunState(S.paused, pause_reason=PauseReason.key_missing)


def test_running_to_done() -> None:
    assert transition(RUNNING, S.done).status is S.done


def test_running_to_failed() -> None:
    assert transition(RUNNING, S.failed).status is S.failed


def test_running_to_cancelled() -> None:
    assert transition(RUNNING, S.cancelled).status is S.cancelled


def test_queued_to_failed_when_the_job_cannot_be_queued() -> None:
    assert transition(QUEUED, S.failed).status is S.failed


def test_awaiting_review_to_queued_clears_waiting_for() -> None:
    assert transition(AWAITING, S.queued) == QUEUED


def test_awaiting_review_to_cancelled() -> None:
    assert transition(AWAITING, S.cancelled) == RunState(S.cancelled)


def test_paused_to_queued_clears_reason() -> None:
    assert transition(PAUSED, S.queued) == QUEUED


def test_paused_to_cancelled() -> None:
    assert transition(PAUSED, S.cancelled) == RunState(S.cancelled)


def test_failed_to_queued() -> None:
    assert transition(FAILED, S.queued) == QUEUED


def test_exactly_the_documented_transitions_are_allowed() -> None:
    assert {
        S.queued: frozenset({S.running, S.failed}),
        S.running: frozenset({S.awaiting_review, S.paused, S.done, S.failed, S.cancelled}),
        S.awaiting_review: frozenset({S.queued, S.cancelled}),
        S.paused: frozenset({S.queued, S.cancelled}),
        S.failed: frozenset({S.queued}),
        S.done: frozenset(),
        S.cancelled: frozenset(),
    } == ALLOWED_TRANSITIONS
    assert frozenset({S.done, S.cancelled}) == FINAL_STATUSES


def _state(status: RunStatus) -> RunState:
    if status is S.paused:
        return PAUSED
    if status is S.awaiting_review:
        return AWAITING
    return RunState(status)


ILLEGAL = [
    (a, b) for a, b in itertools.product(RunStatus, RunStatus) if b not in ALLOWED_TRANSITIONS[a]
]


@pytest.mark.parametrize(("current", "target"), ILLEGAL, ids=[f"{a}->{b}" for a, b in ILLEGAL])
def test_illegal_transitions_rejected(current: RunStatus, target: RunStatus) -> None:
    extra: dict[str, object] = {}
    if target is S.paused:
        extra["pause_reason"] = PauseReason.key_missing
    if target is S.awaiting_review:
        extra["waiting_for"] = WaitingFor.profile_review
    with pytest.raises(IllegalTransitionError):
        transition(_state(current), target, **extra)  # type: ignore[arg-type]


def test_pause_requires_reason() -> None:
    with pytest.raises(InvalidRunStateError, match="pause_reason"):
        transition(RUNNING, S.paused)


def test_awaiting_review_requires_waiting_for() -> None:
    with pytest.raises(InvalidRunStateError, match="waiting_for"):
        transition(RUNNING, S.awaiting_review)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": S.running, "pause_reason": PauseReason.key_rejected},
        {"status": S.done, "waiting_for": WaitingFor.profile_review},
        {
            "status": S.paused,
            "pause_reason": PauseReason.key_missing,
            "waiting_for": WaitingFor.profile_review,
        },
        {"status": S.paused},
        {"status": S.awaiting_review},
    ],
)
def test_reason_fields_only_with_matching_status(kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidRunStateError):
        RunState(**kwargs)  # type: ignore[arg-type]


def test_values_match_database_strings() -> None:
    assert [s.value for s in RunStatus] == [
        "queued",
        "running",
        "awaiting_review",
        "paused",
        "done",
        "failed",
        "cancelled",
    ]
    assert {r.value for r in PauseReason} == {
        "key_missing",
        "key_rejected",
        "out_of_credit",
    }
    assert {w.value for w in WaitingFor} == {"profile_review", "injection_decision"}


def test_R7_paused_accepts_out_of_credit() -> None:
    new = transition(RUNNING, S.paused, pause_reason=PauseReason.out_of_credit)
    assert new == RunState(S.paused, pause_reason=PauseReason.out_of_credit)
    assert transition(new, S.queued) == RunState(S.queued)  # and it can be resumed
