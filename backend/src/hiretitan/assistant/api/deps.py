"""What Mikasa's routers need (002m contracts/rest-api.md)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.assistant.application.ports import AssistantStatus
from hiretitan.assistant.application.turn import TurnDeps


@dataclass(frozen=True, slots=True)
class AssistantApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    turn: TurnDeps
    status: Callable[[], Awaitable[AssistantStatus]]
    now: Callable[[], datetime]
    # the person's own view of a ref (private details included); never sent to the model
    describe: Callable[[str], Awaitable[dict[str, Any] | None]]
