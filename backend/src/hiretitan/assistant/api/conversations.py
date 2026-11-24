"""Mikasa's conversations: start one, list them, read one's messages (002m US1, US5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.platform.web.problems import ProblemError


class ConversationOut(BaseModel):
    id: UUID
    title: str | None
    last_used_at: datetime


class CreatedOut(BaseModel):
    id: UUID


class MessageOut(BaseModel):
    id: UUID
    seq: int
    author: str
    text: str
    status: str
    refs: list[str]
    signals: list[dict[str, Any]]
    error: dict[str, Any] | None
    created_at: datetime


def not_found() -> ProblemError:
    return ProblemError(404, "That conversation does not exist.", reason="not_found")


def create_conversations_router(deps: AssistantApiDeps) -> APIRouter:
    router = APIRouter(prefix="/assistant/conversations", tags=["assistant"])

    @router.post("", response_model=CreatedOut, status_code=201)
    async def start() -> CreatedOut:
        async with deps.sessions() as session:
            row = await ConversationsRepo(session).create(now=deps.now())
            await session.commit()
            return CreatedOut(id=row.id)

    @router.get("", response_model=list[ConversationOut])
    async def recent() -> list[ConversationOut]:
        async with deps.sessions() as session:
            rows = await ConversationsRepo(session).list_recent()
            return [
                ConversationOut(id=r.id, title=r.title, last_used_at=r.last_used_at) for r in rows
            ]

    @router.get("/{conversation_id}/messages", response_model=list[MessageOut])
    async def messages(conversation_id: UUID) -> list[MessageOut]:
        async with deps.sessions() as session:
            if await ConversationsRepo(session).get(conversation_id) is None:
                raise not_found()
            rows = await MessagesRepo(session).list_for(conversation_id)
            return [
                MessageOut(
                    id=r.id,
                    seq=r.seq,
                    author=r.author,
                    text=r.text,
                    status=r.status,
                    refs=[str(ref) for ref in r.refs],
                    signals=list(r.signals),
                    error=r.error,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    return router
