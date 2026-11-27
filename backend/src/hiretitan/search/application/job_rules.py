"""Restoring a hidden job and checking one again with the AI: the rules the routers used to hold
(002 FR-022 restore, the recheck of 002i), shared since 002m with Mikasa's actions."""

from __future__ import annotations

from typing import Final, Protocol
from uuid import UUID

from hiretitan.search.application.pipeline import JobNotFoundError, PipelineRuleError
from hiretitan.search.domain.job_state import JobState

RECHECKABLE: Final = "rules_only_fallback"


class RestoreStore(Protocol):
    async def state_of(self, job_id: UUID) -> JobState | None: ...

    async def mark_restored(self, job_id: UUID) -> None: ...


async def restore_skipped(store: RestoreStore, job_id: UUID) -> None:
    """A job hidden by the rules goes back to Explore, marked as restored. Does not commit."""
    state = await store.state_of(job_id)
    if state is None:
        raise JobNotFoundError(str(job_id))
    if state is not JobState.skipped:
        raise PipelineRuleError("not_skipped", "Only a skipped job can be restored.")
    await store.mark_restored(job_id)


def check_recheckable(state: JobState, decided_by: str | None) -> None:
    """Only a job in Explore that the AI did not check (its search ran on rules only)."""
    if state is not JobState.explore or decided_by != RECHECKABLE:
        raise PipelineRuleError(
            "not_recheckable", "Only a job the AI has not checked can be checked again."
        )
