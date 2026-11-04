"""Things waiting for the user: reviews, decisions and paused work (FR-033)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.setup.application.status import SetupFacts

PAUSE_TITLES = {
    PauseReason.budget_reached: "Paused: monthly AI budget reached",
    PauseReason.key_missing: "Paused: AI key is missing",
    PauseReason.key_rejected: "Paused: AI key was rejected",
}


@dataclass(frozen=True, slots=True)
class ReviewItem:
    id: UUID  # the run's id
    kind: str  # profile_review | injection_decision | paused
    title: str
    target: str  # the page that handles it
    updated_at: datetime


async def build_review_items(runs: list[Run], facts: SetupFacts) -> list[ReviewItem]:
    """Newest first. ``runs`` holds the awaiting-review and paused runs."""
    items: list[ReviewItem] = []
    for run in runs:
        state = run.state
        if state.status is RunStatus.paused and state.pause_reason is not None:
            target = "/settings" if state.pause_reason is PauseReason.budget_reached else "/"
            items.append(
                ReviewItem(
                    run.id, "paused", PAUSE_TITLES[state.pause_reason], target, run.updated_at
                )
            )
        elif state.waiting_for is WaitingFor.injection_decision:
            items.append(
                ReviewItem(
                    run.id,
                    "injection_decision",
                    "Decide what to do about suspicious text in your resume",
                    "/profile",
                    run.updated_at,
                )
            )
        elif state.waiting_for is WaitingFor.profile_review:
            review_id = await facts.open_review_id(run.id)
            if review_id is not None:
                items.append(
                    ReviewItem(
                        run.id,
                        "profile_review",
                        "Review the profile extracted from your resume",
                        f"/profile/review/{review_id}",
                        run.updated_at,
                    )
                )
    return sorted(items, key=lambda item: item.updated_at, reverse=True)
