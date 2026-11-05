"""T025: runs paused for a missing or rejected key resume from their checkpoint once the key
works; runs paused for the budget do not."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypedDict
from uuid import UUID

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.platform.runtime.checkpointer import open_checkpointer
from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus
from hiretitan.platform.runtime.infra.runs_repo import Run, RunsRepo
from hiretitan.platform.runtime.resume_paused import resume_on_startup, resume_paused_runs
from hiretitan.platform.runtime.runner import WorkflowDef, WorkflowRunner


class State(TypedDict, total=False):
    trace: list[str]


@dataclass
class Toy:
    """Node two raises ``AiUnavailable(reason)`` until ``reason`` is set to None."""

    reason: str | None = "key_missing"
    calls: dict[str, int] = field(default_factory=lambda: {"first": 0, "second": 0})

    def build(self, saver: BaseCheckpointSaver[Any]) -> Any:
        async def first(state: State) -> State:
            self.calls["first"] += 1
            return {"trace": ["first"]}

        async def second(state: State) -> State:
            self.calls["second"] += 1
            if self.reason is not None:
                raise AiUnavailable(self.reason)
            return {"trace": [*state["trace"], "second"]}

        graph = StateGraph(State)
        graph.add_node("first", first)
        graph.add_node("second", second)
        graph.add_edge(START, "first")
        graph.add_edge("first", "second")
        graph.add_edge("second", END)
        return graph.compile(checkpointer=saver)


@dataclass
class FakeQueue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class FakeStatus:
    result: str

    async def check(self) -> str:
        return self.result


@pytest.fixture
async def saver(database_url: str) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    async with open_checkpointer(database_url) as checkpointer:
        yield checkpointer


def runner_for(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any], toy: Toy
) -> WorkflowRunner:
    definition = WorkflowDef(toy.build, lambda run: {"trace": []})
    return WorkflowRunner(sessions, saver, {"toy": definition})


async def paused_run(sessions: async_sessionmaker[AsyncSession], runner: WorkflowRunner) -> Run:
    async with sessions() as session:
        run = await RunsRepo(session).create("toy")
        await session.commit()
    await runner.execute(run.id)
    return run


async def status_of(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> RunStatus:
    async with sessions() as session:
        run = await RunsRepo(session).get(run_id)
    assert run is not None
    return run.state.status


async def test_US3_AS3_paused_run_resumes_from_checkpoint_after_key_fixed(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any]
) -> None:
    toy = Toy("key_missing")
    runner = WorkflowRunner(
        sessions, saver, {"toy": WorkflowDef(toy.build, lambda r: {"trace": []})}
    )
    run = await paused_run(sessions, runner)
    assert await status_of(sessions, run.id) is RunStatus.paused

    toy.reason = None  # the user fixed the key
    queue = FakeQueue()
    assert await resume_paused_runs(sessions, queue, PauseReason.key_missing) == 1
    assert queue.enqueued == [run.id]
    assert await status_of(sessions, run.id) is RunStatus.queued

    await runner.execute(run.id)  # what the queued job does
    assert await status_of(sessions, run.id) is RunStatus.done
    assert toy.calls["first"] == 1  # resumed from the checkpoint, not restarted


async def test_budget_paused_runs_untouched_by_key_resume(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any]
) -> None:
    toy = Toy("budget_reached")
    runner = WorkflowRunner(
        sessions, saver, {"toy": WorkflowDef(toy.build, lambda r: {"trace": []})}
    )
    run = await paused_run(sessions, runner)

    queue = FakeQueue()
    assert await resume_paused_runs(sessions, queue, PauseReason.key_missing) == 0
    assert await resume_paused_runs(sessions, queue, PauseReason.key_rejected) == 0
    assert queue.enqueued == []
    assert await status_of(sessions, run.id) is RunStatus.paused


async def test_startup_resumes_key_pauses_only_when_the_key_works(
    sessions: async_sessionmaker[AsyncSession], saver: BaseCheckpointSaver[Any]
) -> None:
    toy = Toy("key_rejected")
    runner = WorkflowRunner(
        sessions, saver, {"toy": WorkflowDef(toy.build, lambda r: {"trace": []})}
    )
    run = await paused_run(sessions, runner)

    queue = FakeQueue()
    await resume_on_startup(FakeStatus("rejected"), sessions, queue)
    assert queue.enqueued == []
    assert await status_of(sessions, run.id) is RunStatus.paused

    await resume_on_startup(FakeStatus("working"), sessions, queue)
    assert queue.enqueued == [run.id]
    assert await status_of(sessions, run.id) is RunStatus.queued
