"""``GET /events``: the server-sent event stream the SPA listens to."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import EventSourceResponse, ServerSentEvent

from hiretitan.platform.runtime.domain.run_state import (
    IllegalTransitionError,
    RunStatus,
    WaitingFor,
)
from hiretitan.platform.runtime.events import listen
from hiretitan.platform.runtime.infra.runs_repo import Run, RunsRepo
from hiretitan.platform.runtime.runner import RunQueue, resume_run
from hiretitan.platform.web.problems import ProblemError


def create_events_router(database_url: str) -> APIRouter:
    router = APIRouter()

    @router.get("/events")
    async def events() -> EventSourceResponse:
        async def stream() -> AsyncIterator[ServerSentEvent]:
            async with listen(database_url) as events_iter:
                yield ServerSentEvent(comment="ready")  # subscribed: nothing is missed now
                async for event in events_iter:
                    yield ServerSentEvent(event=event.name, data=json.dumps(event.data))

        return EventSourceResponse(stream())

    return router


# ---- runs (contracts/rest-api.md, "Workflow runs") ---------------------------------------------
class RunOut(BaseModel):
    id: UUID
    workflow: str
    status: str
    pause_reason: str | None
    waiting_for: str | None
    current_step: str | None
    error: str | None
    updated_at: datetime


class DecisionIn(BaseModel):
    decision: Literal["continue_extraction", "manual_entry"]


def create_runs_router(sessions: async_sessionmaker[AsyncSession], queue: RunQueue) -> APIRouter:
    router = APIRouter(tags=["runs"])

    async def load(run_id: UUID) -> Run:
        async with sessions() as session:
            run = await RunsRepo(session).get(run_id)
        if run is None:
            raise ProblemError(404, f"Run {run_id} was not found.")
        return run

    @router.get("/runs/{run_id}")
    async def get_run(run_id: UUID) -> RunOut:
        run = await load(run_id)
        state = run.state
        return RunOut(
            id=run.id,
            workflow=run.workflow,
            status=state.status.value,
            pause_reason=state.pause_reason.value if state.pause_reason else None,
            waiting_for=state.waiting_for.value if state.waiting_for else None,
            current_step=run.current_step,
            error=run.error,
            updated_at=run.updated_at,
        )

    @router.post("/runs/{run_id}/decision", status_code=202)
    async def decide(run_id: UUID, body: DecisionIn) -> dict[str, str]:
        run = await load(run_id)
        if run.state.waiting_for is not WaitingFor.injection_decision:
            raise ProblemError(409, "This run is not waiting for that decision.")
        try:
            await resume_run(sessions, queue, run_id, {"decision": body.decision})
        except IllegalTransitionError:
            raise ProblemError(409, "This run is not waiting for that decision.") from None
        return {"run_id": str(run_id)}

    @router.post("/runs/{run_id}/retry", status_code=202)
    async def retry(run_id: UUID) -> dict[str, str]:
        run = await load(run_id)
        if run.state.status is not RunStatus.failed:
            raise ProblemError(409, "Only a failed run can be tried again.")
        async with sessions() as session:
            await RunsRepo(session).transition(run_id, RunStatus.queued)
            await session.commit()
        await queue.enqueue(run_id)
        return {"run_id": str(run_id)}

    return router
