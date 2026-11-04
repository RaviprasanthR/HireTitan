"""Resume runs that paused because the AI was unavailable (FR-030, US3).

A run paused for a missing or rejected key goes back on the queue once the key works and
continues from its LangGraph checkpoint. Runs paused for the budget stay paused: the key
being fixed does not change the budget.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.runtime.runner import RunQueue

KEY_PAUSES = (PauseReason.key_missing, PauseReason.key_rejected)


class KeyStatus(Protocol):
    async def check(self) -> str: ...


async def resume_paused_runs(
    sessions: async_sessionmaker[AsyncSession], queue: RunQueue, reason: PauseReason
) -> int:
    """Re-queue every paused run with this ``pause_reason``; returns how many."""
    async with sessions() as session:
        repo = RunsRepo(session)
        runs = [
            run
            for run in await repo.list_by_status(RunStatus.paused)
            if run.state.pause_reason is reason
        ]
        for run in runs:
            await repo.transition(run.id, RunStatus.queued)
        await session.commit()
    for run in runs:
        await queue.enqueue(run.id)
    return len(runs)


async def resume_on_startup(
    status: KeyStatus, sessions: async_sessionmaker[AsyncSession], queue: RunQueue
) -> None:
    """Worker start-up: check the key, and if it works resume the runs it had paused."""
    if await status.check() != "working":
        return
    for reason in KEY_PAUSES:
        await resume_paused_runs(sessions, queue, reason)
