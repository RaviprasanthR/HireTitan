"""T009: the job state machine (data-model.md, "State transitions")."""

from __future__ import annotations

from datetime import date

import pytest

from hiretitan.search.domain.job_state import (
    IllegalJobTransitionError,
    JobState,
    apply_found_again,
    apply_new,
    transition,
)

S = JobState


def test_new_job_rules_skip_it() -> None:
    assert apply_new(skipped=True) == JobState.skipped


def test_new_job_passing_goes_to_explore() -> None:
    assert apply_new(skipped=False) == JobState.explore


def test_skipped_to_explore_is_a_restore() -> None:
    new = transition(S.skipped, S.explore)
    assert new.state is S.explore
    assert new.restored is True


def test_explore_to_skipped_when_a_later_ai_check_says_not_relevant() -> None:
    assert transition(S.explore, S.skipped).state is S.skipped


def test_explore_to_applied_needs_a_date() -> None:
    new = transition(S.explore, S.applied, applied_on=date(2026, 11, 5))
    assert new.state is S.applied
    assert new.applied_on == date(2026, 11, 5)


def test_US5_skipped_to_applied_is_allowed() -> None:
    new = transition(S.skipped, S.applied, applied_on=date(2026, 11, 5))
    assert new.state is S.applied
    assert new.applied_on == date(2026, 11, 5)


def test_explore_to_applied_without_a_date_rejected() -> None:
    with pytest.raises(IllegalJobTransitionError):
        transition(S.explore, S.applied)


def test_applied_to_explore_is_an_undo() -> None:
    new = transition(S.applied, S.explore)
    assert new.state is S.explore
    assert new.applied_on is None
    assert new.restored is False


@pytest.mark.parametrize("state", [S.explore, S.skipped, S.applied])
def test_any_live_state_can_be_deleted(state: JobState) -> None:
    assert transition(state, S.deleted).state is S.deleted


def test_US1_AS6_seen_again_keeps_state() -> None:
    for state in (S.explore, S.skipped, S.applied, S.deleted):
        assert apply_found_again(state) is state


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.deleted, S.explore),
        (S.deleted, S.skipped),
        (S.deleted, S.applied),
        (S.deleted, S.deleted),
        (S.skipped, S.skipped),
        (S.explore, S.explore),
        (S.applied, S.skipped),
        (S.applied, S.applied),
    ],
)
def test_illegal_transitions_rejected(current: JobState, target: JobState) -> None:
    with pytest.raises(IllegalJobTransitionError):
        transition(current, target, applied_on=date(2026, 11, 5))


# --- 002d: the inquired state (data-model.md, "Job state (changed)") ------------------------


@pytest.mark.parametrize("state", [S.explore, S.skipped])
def test_US2_AS1_explore_and_skipped_can_become_inquired(state: JobState) -> None:
    new = transition(state, S.inquired, inquired_on=date(2026, 11, 12))

    assert new.state is S.inquired
    assert new.inquired_on == date(2026, 11, 12)
    assert new.applied_on is None


def test_US2_AS2_inquired_can_become_applied() -> None:
    new = transition(S.inquired, S.applied, applied_on=date(2026, 11, 13))

    assert new.state is S.applied
    assert new.applied_on == date(2026, 11, 13)
    assert new.inquired_on is None  # moving on clears the inquiry date


def test_FR007_applied_cannot_become_inquired() -> None:
    with pytest.raises(IllegalJobTransitionError):
        transition(S.applied, S.inquired, inquired_on=date(2026, 11, 12))


def test_US2_AS3_undo_inquired_returns_to_explore() -> None:
    new = transition(S.inquired, S.explore)

    assert new.state is S.explore
    assert new.inquired_on is None
    assert new.applied_on is None
    assert new.restored is False


def test_inquired_needs_a_date() -> None:
    with pytest.raises(IllegalJobTransitionError, match="inquired"):
        transition(S.explore, S.inquired)


def test_an_inquired_job_can_be_deleted() -> None:
    assert transition(S.inquired, S.deleted).state is S.deleted


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.inquired, S.skipped),
        (S.inquired, S.inquired),
        (S.deleted, S.inquired),
    ],
)
def test_illegal_transitions_involving_inquired_are_rejected(
    current: JobState, target: JobState
) -> None:
    with pytest.raises(IllegalJobTransitionError):
        transition(current, target, applied_on=date(2026, 11, 5), inquired_on=date(2026, 11, 5))


def test_seen_again_keeps_an_inquired_job_inquired() -> None:
    assert apply_found_again(S.inquired) is S.inquired
