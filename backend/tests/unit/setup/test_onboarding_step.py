"""T071: which setup card to show (FR-037, FR-038, FR-040)."""

from __future__ import annotations

import pytest

from hiretitan.setup.domain.onboarding import setup_step


def step(**facts: bool) -> object:
    base = {
        "completed": False,
        "has_name": True,
        "open_review": False,
        "active_run": False,
        "profile_confirmed": False,
    }
    return setup_step(**{**base, **facts})


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        ({"has_name": False}, 1),
        ({}, 2),  # named, nothing uploaded yet
        ({"active_run": True}, 2),  # a resume is being read, paused or awaiting a decision
        ({"open_review": True}, 3),
        ({"open_review": True, "active_run": True}, 3),
        ({"profile_confirmed": True}, 4),
        ({"profile_confirmed": True, "open_review": True}, 3),  # a re-upload during setup
        ({"profile_confirmed": True, "active_run": True}, 2),
        ({"has_name": False, "open_review": True}, 1),
    ],
)
def test_FR038_step_order(facts: dict[str, bool], expected: int) -> None:
    assert step(**facts) == expected


@pytest.mark.parametrize(
    "facts",
    [
        {},
        {"has_name": False},
        {"open_review": True},
        {"active_run": True},
        {"profile_confirmed": True},
    ],
)
def test_FR040_completed_wins_over_everything(facts: dict[str, bool]) -> None:
    assert step(completed=True, **facts) == "done"
