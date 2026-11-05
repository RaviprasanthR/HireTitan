"""Which setup card to show (FR-037, FR-038, FR-040). Pure."""

from __future__ import annotations

from typing import Literal

SetupStep = Literal[1, 2, 3, 4, "done"]


def setup_step(
    *,
    completed: bool,
    has_name: bool,
    open_review: bool,
    active_run: bool,
    profile_confirmed: bool,
) -> SetupStep:
    """The first rule that matches wins, so leaving and coming back lands on the same card.

    ``active_run`` means a resume is being read, is paused, or waits for the injection
    decision; ``open_review`` means a profile review (extracted or typed) is open.
    """
    if completed:
        return "done"
    if not has_name:
        return 1
    if open_review:
        return 3
    if active_run or not profile_confirmed:
        return 2
    return 4
