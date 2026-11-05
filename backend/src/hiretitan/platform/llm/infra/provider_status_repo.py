"""Repository for ``app.provider_status``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.llm.infra.models import ProviderStatusRow


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    provider: str
    status: str
    message: str | None
    checked_at: datetime | None


class ProviderStatusRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, provider: str) -> ProviderStatus | None:
        row = await self._session.get(ProviderStatusRow, provider)
        if row is None:
            return None
        return ProviderStatus(row.provider, row.status, row.message, row.checked_at)

    async def set(
        self,
        provider: str,
        status: str,
        message: str | None,
        *,
        checked_at: datetime | None = None,
    ) -> None:
        """Insert or update. ``message`` must be a fixed, user-facing text, never a key."""
        values = {"status": status, "message": message, "checked_at": checked_at}
        statement = insert(ProviderStatusRow).values(provider=provider, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["provider"], set_=values)
        )
        await self._session.flush()
