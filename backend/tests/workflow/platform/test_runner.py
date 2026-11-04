"""T014: the generic workflow runner, on a toy two-node graph and a real database.

Each ``execute`` call stands for one job run by a worker, so calling it again with a new
runner and checkpointer stands for a worker restart.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypedDict
from uuid import UUID

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.platform.runtime.checkpointer import open_checkpointer
from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import Run, RunsRepo
from hiretitan.platform.runtime.runner import (
    RETRY_DELAYS_SECONDS,
    WorkflowDef,
    WorkflowRunner,
    resume_run,
    retry_delay_seconds,
)


class SimulatedCrash(BaseException):
    """Not an ``Exception``: the runner must not catch it, like a SIGKILL."""


class State(TypedDict, total=False):
    trace: list[str]


@dataclass
class Toy:
    """A two-node graph whose second node behaviour the test picks."""

    calls: dict[str, int] = field(default_factory=lambda: {"first": 0, "second": 0})
    second: Any = None

    def build(self, saver: BaseCheckpointSaver[Any]) -> Any:
        async def first(state: State) -> State:
            self.calls["first"] += 1
            return {"trace": ["first"]}

        async def second(state: State) -> State:
            self.calls["second"] += 1
            return await self.second(state)

        graph = StateGraph(State)
        graph.add_node("first", first)
        graph.add_node("second", second)
        graph.add_edge(START, "first")
        graph.add_edge("first", "second")
        graph.add_edge("second", END)
        return graph.compile(checkpointer=saver)

    def definition(self) -> WorkflowDef:
        return WorkflowDef(build=self.build, initial_input=lambda run: {"trace": []})


@dataclass
class FakeQueue:
    enqueued: list[tuple[UUID, Any]] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append((run_id, resume))


@pytest.fixture
async def saver(database_url: str) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    async with open_checkpointer(database_url) as checkpointer:
        yield checkpointer


def make_runner(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any], toy: Toy
) -> WorkflowRunner:
    return WorkflowRunner(sessions, saver, {"toy": toy.definition()})


async def new_run(sessions: async_sessionmaker[AsyncSession]) -> Run:
    async with sessions() as session:
        run = await RunsRepo(session).create("toy")
        await session.commit()
        return run


async def current(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> Run:
    async with sessions() as session:
        run = await RunsRepo(session).get(run_id)
    assert run is not None
    return run


async def test_FR013_run_survives_worker_restart(
    sessions: async_sessionmaker[AsyncSession], database_url: str
) -> None:
    toy = Toy()
    crash = True

    async def second(state: State) -> State:
        if crash:
            raise SimulatedCrash
        return {"trace": [*state["trace"], "second"]}

    toy.second = second
    run = await new_run(sessions)

    async with open_checkpointer(database_url) as first_worker:
        with pytest.raises(SimulatedCrash):
            await make_runner(sessions, first_worker, toy).execute(run.id)
    assert (await current(sessions, run.id)).state.status is RunStatus.running

    crash = False
    async with open_checkpointer(database_url) as second_worker:
        await make_runner(sessions, second_worker, toy).execute(run.id)

    assert (await current(sessions, run.id)).state.status is RunStatus.done
    assert toy.calls["first"] == 1  # the first node was not repeated
    assert toy.calls["second"] == 2


async def test_interrupt_sets_awaiting_review(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any]
) -> None:
    toy = Toy()

    async def second(state: State) -> State:
        interrupt({"waiting_for": "profile_review"})
        return {}

    toy.second = second
    run = await new_run(sessions)
    await make_runner(sessions, saver, toy).execute(run.id)

    state = (await current(sessions, run.id)).state
    assert state.status is RunStatus.awaiting_review
    assert state.waiting_for is WaitingFor.profile_review


async def test_resume_continues_after_interrupt(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any]
) -> None:
    toy = Toy()
    seen: list[Any] = []

    async def second(state: State) -> State:
        seen.append(interrupt({"waiting_for": "injection_decision"}))
        return {}

    toy.second = second
    run = await new_run(sessions)
    runner = make_runner(sessions, saver, toy)
    await runner.execute(run.id)

    queue = FakeQueue()
    await resume_run(sessions, queue, run.id, {"decision": "continue"})
    assert queue.enqueued == [(run.id, {"decision": "continue"})]
    assert (await current(sessions, run.id)).state.status is RunStatus.queued

    await runner.execute(run.id, resume={"decision": "continue"})
    assert (await current(sessions, run.id)).state.status is RunStatus.done
    assert seen == [{"decision": "continue"}]
    assert toy.calls["first"] == 1


async def test_FR030_ai_unavailable_pauses_not_fails(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any]
) -> None:
    toy = Toy()

    async def second(state: State) -> State:
        raise AiUnavailable("budget_reached")

    toy.second = second
    run = await new_run(sessions)
    await make_runner(sessions, saver, toy).execute(run.id)  # the job ends normally

    state = (await current(sessions, run.id)).state
    assert state.status is RunStatus.paused
    assert state.pause_reason is PauseReason.budget_reached


async def test_retries_then_failed(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any]
) -> None:
    toy = Toy()

    async def second(state: State) -> State:
        raise ValueError("secret internal detail")

    toy.second = second
    run = await new_run(sessions)
    runner = make_runner(sessions, saver, toy)
    max_attempts = len(RETRY_DELAYS_SECONDS) + 1

    for attempt in range(1, max_attempts):
        with pytest.raises(ValueError):
            await runner.execute(run.id, attempt=attempt, max_attempts=max_attempts)
        assert (await current(sessions, run.id)).state.status is RunStatus.running

    await runner.execute(run.id, attempt=max_attempts, max_attempts=max_attempts)
    final = await current(sessions, run.id)
    assert final.state.status is RunStatus.failed
    assert final.error
    assert "secret internal detail" not in final.error  # user-facing message


def test_retry_delays_are_10s_1min_5min() -> None:
    assert [retry_delay_seconds(n) for n in (1, 2, 3)] == [10, 60, 300]
    assert retry_delay_seconds(4) is None
