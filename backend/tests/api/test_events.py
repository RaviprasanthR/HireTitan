"""T015: the SSE stream ``GET /api/v1/events`` and the NOTIFY/LISTEN behind it."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hiretitan.platform.runtime.api import create_events_router
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.events import EventPublisher, run_notifier
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo


@asynccontextmanager
async def serve(app: FastAPI) -> AsyncIterator[str]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 - uvicorn exposes no startup event
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def next_event(lines: AsyncIterator[str]) -> tuple[str, dict[str, object]]:
    name = ""
    async for line in lines:
        if line.startswith("event:"):
            name = line.removeprefix("event:").strip()
        elif line.startswith("data:") and name:
            return name, json.loads(line.removeprefix("data:").strip())
    raise AssertionError("stream ended")


async def test_run_status_change_streams_run_updated(
    database_url: str,
    committed_engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    app = FastAPI()
    app.include_router(create_events_router(database_url), prefix="/api/v1")
    notify = run_notifier(EventPublisher(committed_engine))
    async with sessions() as session:
        run = await RunsRepo(session).create("toy")
        await session.commit()

    async with (
        serve(app) as base,
        httpx.AsyncClient(base_url=base, timeout=10) as client,
        client.stream("GET", "/api/v1/events") as response,
    ):
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = response.aiter_lines()
        async for line in lines:  # the server is listening once it sends ": ready"
            if line.startswith(":") and "ready" in line:
                break
        async with sessions() as session:
            moved = await RunsRepo(session).transition(run.id, RunStatus.running)
            await session.commit()
        await notify(moved)
        name, data = await asyncio.wait_for(next_event(lines), 5)

    assert name == "run.updated"
    assert data == {
        "run_id": str(run.id),
        "workflow": "toy",
        "status": "running",
        "current_step": None,
        "pause_reason": None,
        "waiting_for": None,
    }


async def test_search_batch_done_streams(database_url: str, committed_engine: AsyncEngine) -> None:
    app = FastAPI()
    app.include_router(create_events_router(database_url), prefix="/api/v1")
    progress = {"search_run_id": "run-1", "batches_done": 1, "jobs_found": 8, "added": 3}

    async with (
        serve(app) as base,
        httpx.AsyncClient(base_url=base, timeout=10) as client,
        client.stream("GET", "/api/v1/events") as response,
    ):
        lines = response.aiter_lines()
        async for line in lines:
            if line.startswith(":") and "ready" in line:
                break
        await EventPublisher(committed_engine).publish("search.batch_done", progress)
        name, data = await asyncio.wait_for(next_event(lines), 5)

    assert (name, data) == ("search.batch_done", progress)
