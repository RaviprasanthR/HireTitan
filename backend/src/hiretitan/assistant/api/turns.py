"""``POST /assistant/conversations/{id}/turns``: send a message and stream Mikasa's reply
(002m FR-002, contracts/rest-api.md "Turn stream").

The checks that refuse a message (too long, looks like a posting, a turn already running, the AI
not usable) answer before the stream starts, as problem documents. Closing the request stops
the turn; the reply written so far is kept as ``stopped``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse, ServerSentEvent

from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.application.turn import (
    ConversationNotFoundError,
    EmptyMessageError,
    LooksLikePostingError,
    MessageTooLongError,
    TurnError,
    TurnEvent,
    TurnRunningError,
    begin,
    run_turn,
)
from hiretitan.platform.web.problems import ProblemError

_REFUSALS: dict[type[TurnError], tuple[int, str]] = {
    ConversationNotFoundError: (404, "That conversation does not exist."),
    TurnRunningError: (409, "Mikasa is still answering your last message."),
    MessageTooLongError: (422, "A message can be at most 2,000 characters."),
    EmptyMessageError: (422, "Write a message first."),
    LooksLikePostingError: (
        422,
        "That looks like a job posting. Use Paste a job description, so it is read as a "
        "posting and never sent to the AI as your words.",
    ),
}


class TurnIn(BaseModel):
    text: str = Field(max_length=10_000)  # the 2,000 limit answers with its own message
    page: str = Field("/", max_length=500)


def _event(event: TurnEvent) -> ServerSentEvent:
    data: dict[str, Any] = {k: v for k, v in asdict(event).items() if k != "name"}
    return ServerSentEvent(event=event.name, data=json.dumps(data, default=str))


def create_turns_router(deps: AssistantApiDeps) -> APIRouter:
    router = APIRouter(prefix="/assistant/conversations", tags=["assistant"])

    @router.post("/{conversation_id}/turns")
    async def send(conversation_id: UUID, body: TurnIn) -> EventSourceResponse:
        status = await deps.status()
        if not status.available:
            raise ProblemError(
                503,
                "Mikasa can't answer right now.",
                reason="ai_unavailable",
                status_reason=status.reason,
                provider_message=status.provider_message,
            )
        try:
            await begin(deps.turn, conversation_id, body.text)
        except TurnError as error:
            code, detail = _REFUSALS[type(error)]
            raise ProblemError(code, detail, reason=error.reason) from error

        async def stream() -> AsyncIterator[ServerSentEvent]:
            async for event in run_turn(deps.turn, conversation_id, page=body.page):
                yield _event(event)

        return EventSourceResponse(stream())

    return router
