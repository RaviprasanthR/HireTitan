"""Generic workflow runner (FR-013, FR-030).

``WorkflowRunner.execute`` is one job run: it moves the run to ``running``, drives the
workflow's LangGraph graph with ``thread_id = run_id`` (so a restarted worker continues
from the last checkpoint), and records how it ended:

* graph finished            -> ``done``
* graph called ``interrupt``  -> ``awaiting_review`` with ``waiting_for``
* ``AiUnavailable(reason)``   -> ``paused`` with ``pause_reason`` (the job ends normally)
* any other exception         -> re-raised so the queue retries; on the last attempt the run
  becomes ``failed`` with a user-facing message (never the exception text).

A process kill is not an ``Exception``, so it leaves the run ``running`` and the next job
picks it up.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.platform.runtime.domain.run_state import (
    PauseReason,
    RunStatus,
    WaitingFor,
)
from hiretitan.platform.runtime.infra.runs_repo import Run, RunsRepo

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS: Final = (10, 60, 300)
FAILURE_MESSAGE: Final = "Something went wrong while running this. You can try again."
INTERRUPT_KEY: Final = "__interrupt__"

Notify = Callable[[Run], Awaitable[None]]


def retry_delay_seconds(attempt: int) -> int | None:
    """Seconds to wait after failed attempt number ``attempt`` (1-based); None = give up."""
    if 1 <= attempt <= len(RETRY_DELAYS_SECONDS):
        return RETRY_DELAYS_SECONDS[attempt - 1]
    return None


@dataclass(frozen=True, slots=True)
class WorkflowDef:
    """A workflow the runner can run: a graph builder and its first input."""

    build: Callable[[BaseCheckpointSaver[Any]], Any]
    initial_input: Callable[[Run], dict[str, Any]]
    # LangGraph stops a run after this many steps; a long loop (a search) needs more than 25
    recursion_limit: int | None = None


class RunQueue(Protocol):
    async def enqueue(self, run_id: UUID, resume: Any = None) -> None: ...


class WorkflowRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        checkpointer: BaseCheckpointSaver[Any],
        registry: Mapping[str, WorkflowDef],
        notify: Notify | None = None,
    ) -> None:
        self._sessions = sessions
        self._checkpointer = checkpointer
        self._registry = registry
        self._notify = notify

    async def _move(self, run_id: UUID, target: RunStatus, **kwargs: Any) -> Run:
        async with self._sessions() as session:
            run = await RunsRepo(session).transition(run_id, target, **kwargs)
            await session.commit()
        if self._notify is not None:
            await self._notify(run)
        return run

    async def _start(self, run_id: UUID) -> Run | None:
        """Mark the run running; None if it isn't ours to run (already finished, paused...)."""
        async with self._sessions() as session:
            run = await RunsRepo(session).get(run_id)
        if run is None:
            logger.warning("run not found", extra={"run_id": str(run_id)})
            return None
        if run.state.status is RunStatus.running:  # retry, or a worker died mid-run
            return run
        if run.state.status is RunStatus.queued:
            return await self._move(run_id, RunStatus.running)
        logger.info(
            "run not runnable", extra={"run_id": str(run_id), "status": run.state.status.value}
        )
        return None

    async def execute(
        self,
        run_id: UUID,
        *,
        resume: Any = None,
        attempt: int = 1,
        max_attempts: int = len(RETRY_DELAYS_SECONDS) + 1,
    ) -> None:
        run = await self._start(run_id)
        if run is None:
            return
        try:
            result = await self._drive(run, resume)
        except AiUnavailable as unavailable:
            await self._move(run_id, RunStatus.paused, pause_reason=PauseReason(unavailable.reason))
            return
        except Exception:
            if attempt >= max_attempts:
                logger.exception("run failed", extra={"run_id": str(run_id)})
                await self._move(run_id, RunStatus.failed, error=FAILURE_MESSAGE)
                return
            raise
        await self._finish(run_id, result)

    async def _drive(self, run: Run, resume: Any) -> dict[str, Any]:
        definition = self._registry[run.workflow]
        graph = definition.build(self._checkpointer)
        config: dict[str, Any] = {"configurable": {"thread_id": str(run.id)}}
        if definition.recursion_limit is not None:
            config["recursion_limit"] = definition.recursion_limit
        if resume is not None:
            graph_input: Any = Command(resume=resume)
        elif (await graph.aget_state(config)).next:
            graph_input = None  # continue from the last checkpoint
        else:
            graph_input = definition.initial_input(run)
        result: dict[str, Any] = await graph.ainvoke(graph_input, config)
        return result

    async def _finish(self, run_id: UUID, result: dict[str, Any]) -> None:
        interrupts = result.get(INTERRUPT_KEY)
        if not interrupts:
            await self._move(run_id, RunStatus.done)
            return
        payload = interrupts[0].value
        waiting_for = WaitingFor(payload["waiting_for"])
        await self._move(run_id, RunStatus.awaiting_review, waiting_for=waiting_for)


async def resume_run(
    sessions: async_sessionmaker[AsyncSession],
    queue: RunQueue,
    run_id: UUID,
    decision: Any,
) -> Run:
    """Re-queue a run that is waiting for the user, carrying their decision."""
    async with sessions() as session:
        run = await RunsRepo(session).transition(run_id, RunStatus.queued)
        await session.commit()
    await queue.enqueue(run_id, decision)
    return run
