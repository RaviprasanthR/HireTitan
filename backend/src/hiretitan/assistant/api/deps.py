"""What Mikasa's routers need (002m contracts/rest-api.md)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.assistant.application.ports import (
    AssistantStatus,
    CardUnitFactory,
    StagedFlow,
    UndoUnitFactory,
)
from hiretitan.assistant.application.turn import TurnDeps


@dataclass(frozen=True, slots=True)
class AssistantApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    turn: TurnDeps
    status: Callable[[], Awaitable[AssistantStatus]]
    now: Callable[[], datetime]
    # the person's own view of a ref (private details included); never sent to the model
    describe: Callable[[str], Awaitable[dict[str, Any] | None]]
    cards: CardUnitFactory
    undo: UndoUnitFactory
    # (conversation, the pasted fields) -> the change, or {"errors": [...]} (FR-021)
    paste: Callable[[UUID, dict[str, Any]], Awaitable[dict[str, Any]]]
    publish: Callable[[list[list[str]]], Awaitable[None]] | None = None
    # the post-to-draft flow of a conversation (002m)
    staged: StagedFlow | None = None
