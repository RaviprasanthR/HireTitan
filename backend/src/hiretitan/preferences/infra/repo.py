"""Repository for the preferences singleton. Implements ``PreferencesStore``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.preferences.application.service import StoredPreferences, get_default_country
from hiretitan.preferences.domain.model import Preferences
from hiretitan.preferences.domain.serialization import preferences_from_json, preferences_to_json
from hiretitan.preferences.infra.models import PreferencesRow


class PreferencesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self) -> StoredPreferences | None:
        row = (await self._session.execute(select(PreferencesRow))).scalar_one_or_none()
        if row is None or row.saved_at is None:
            return None
        return StoredPreferences(preferences_from_json(row.content), row.saved_at)

    async def write(self, prefs: Preferences, saved_at: datetime) -> None:
        values = {"content": preferences_to_json(prefs), "saved_at": saved_at}
        statement = pg_insert(PreferencesRow).values(**values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["singleton"], set_=values)
        )
        await self._session.flush()


def default_country_provider(
    sessions: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[str]]:
    """W1's ``DefaultCountryProvider``: reads the saved country each time it is asked."""

    async def provider() -> str:
        async with sessions() as session:
            return await get_default_country(PreferencesRepo(session))

    return provider
