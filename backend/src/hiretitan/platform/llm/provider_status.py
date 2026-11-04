"""Provider status (FR-029): is the AI key missing, working, rejected or unreachable?

The messages are fixed texts, so a key can never end up in the database, an event or a log.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.openai_adapter import PROVIDER, KeyCheck

MESSAGES: Final = {
    "unknown": None,
    "working": None,
    "missing": "No API key is set. Add OPENAI_API_KEY to your .env file.",
    "rejected": "The provider rejected the API key. Check OPENAI_API_KEY in your .env file.",
    "unreachable": "The provider could not be reached. Check your internet connection.",
}

Publish = Callable[[str, dict[str, Any]], Awaitable[None]]


class KeyChecker(Protocol):
    async def check_key(self) -> KeyCheck: ...


class ProviderStatusService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        checker: KeyChecker,
        *,
        has_key: bool | Callable[[], bool],
        publish: Publish,
        provider: str = PROVIDER,
    ) -> None:
        self._sessions = sessions
        self._checker = checker
        self._has_key = has_key if callable(has_key) else (lambda: has_key)
        self._publish = publish
        self._provider = provider

    async def _write(self, status: str) -> None:
        async with self._sessions() as session:
            await ProviderStatusRepo(session).set(
                self._provider, status, MESSAGES[status], checked_at=datetime.now(UTC)
            )
            await session.commit()
        await self._publish("status.updated", {"ai_status": status})

    async def check(self) -> str:
        """Check the key (no network when it is missing) and record the result."""
        status: str = await self._checker.check_key() if self._has_key() else "missing"
        await self._write(status)
        return status

    async def mark_rejected(self) -> None:
        """A real call got 401/403: record it without another network call."""
        await self._write("rejected")
