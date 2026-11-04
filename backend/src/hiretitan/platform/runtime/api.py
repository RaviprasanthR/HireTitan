"""``GET /events``: the server-sent event stream the SPA listens to."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette import EventSourceResponse, ServerSentEvent

from hiretitan.platform.runtime.events import listen


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
