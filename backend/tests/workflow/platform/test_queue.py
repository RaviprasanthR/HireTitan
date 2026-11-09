"""T014: the Procrastinate wiring (migration 0003, task, retry strategy) against a real database."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.runtime.checkpointer import open_checkpointer
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.runtime.procrastinate import RunRetry, create_runtime
from hiretitan.platform.runtime.runner import WorkflowDef, WorkflowRunner


class State(TypedDict, total=False):
    done: bool


def build(saver: BaseCheckpointSaver[Any]) -> Any:
    async def only(state: State) -> State:
        return {"done": True}

    graph = StateGraph(State)
    graph.add_node("only", only)
    graph.add_edge(START, "only")
    graph.add_edge("only", END)
    return graph.compile(checkpointer=saver)


async def test_migration_0003_creates_job_tables(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        found = await session.scalar(text("SELECT to_regclass('public.procrastinate_jobs')"))
    assert found is not None


async def test_queued_job_runs_the_workflow(
    sessions: async_sessionmaker[AsyncSession], database_url: str
) -> None:
    runtime = create_runtime(database_url)
    registry = {"toy": WorkflowDef(build=build, initial_input=lambda run: {})}
    async with sessions() as session:
        run = await RunsRepo(session).create("toy")
        await session.commit()

    async with open_checkpointer(database_url) as saver, runtime.app.open_async():
        runtime.holder.runner = WorkflowRunner(sessions, saver, registry)
        await runtime.queue.enqueue(run.id)
        await runtime.app.run_worker_async(wait=False)

    async with sessions() as session:
        finished = await RunsRepo(session).get(run.id)
    assert finished is not None
    assert finished.state.status is RunStatus.done


def test_retry_strategy_follows_the_delay_schedule() -> None:
    strategy = RunRetry()
    now = datetime.now(UTC)
    seconds: list[int | None] = []
    for attempts in range(4):
        job = cast(Any, SimpleNamespace(id=1, attempts=attempts))
        decision = strategy.get_retry_decision(exception=ValueError(), job=job)
        if decision is None:
            seconds.append(None)
        else:
            assert decision.retry_at is not None
            seconds.append(round((decision.retry_at - now).total_seconds() / 10) * 10)
    assert seconds == [10, 60, 300, None]


async def test_worker_main_starts_checks_the_key_and_exits_when_idle(
    database_url: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    from hiretitan.platform.config.settings import Settings
    from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
    from hiretitan.worker_main import run_worker

    settings = Settings(DATABASE_URL=database_url, HIRETITAN_LLM="fake")
    await run_worker(settings, wait=False)

    async with sessions() as session:
        status = await ProviderStatusRepo(session).get("fake")
    assert status is not None
    assert status.status == "working"
