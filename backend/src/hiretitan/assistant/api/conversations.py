"""Mikasa's conversations: start one, list them, read one's messages (002m US1, US5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.infra.repos import (
    CardsRepo,
    ChangesRepo,
    ConversationsRepo,
    MessagesRepo,
)
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
    # what the person's message led to: cards to confirm and changes with their Undo (US5)
    cards: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []


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
            now = deps.now()
            cards: dict[UUID, list[dict[str, Any]]] = {}
            for card in await CardsRepo(session).list_for(conversation_id):
                open_ = card.state == "proposed" and now < card.expires_at
                cards.setdefault(card.message_id, []).append(
                    {
                        "card_id": str(card.id),
                        "summary": card.summary,
                        "items": card.items,
                        "state": card.state if open_ or card.state != "proposed" else "expired",
                        "expires_at": card.expires_at.isoformat(),
                        "result": card.result,
                    }
                )
            changes: dict[UUID, list[dict[str, Any]]] = {}
            for change in await ChangesRepo(session).list_for(conversation_id):
                if change.message_id is None:
                    continue  # a card's change shows under its card
                changes.setdefault(change.message_id, []).append(
                    {
                        "change_id": str(change.id),
                        "action": change.action,
                        "summary": change.summary,
                        "undo_until": change.undoable_until.isoformat()
                        if change.undoable_until
                        else None,
                        "undone": change.undone_at is not None,
                    }
                )
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
                    cards=cards.get(r.id, []),
                    changes=changes.get(r.id, []),
                )
                for r in rows
            ]

    return router
