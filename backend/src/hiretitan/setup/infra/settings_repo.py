"""Repository for the settings singleton (the person's name and the setup state)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.setup.application.onboarding import OnboardingRecord
from hiretitan.setup.infra.models import SettingsRow


class SettingsRepo:
    """The onboarding record: display name and when setup was completed."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_onboarding(self) -> OnboardingRecord:
        row = (await self._session.execute(select(SettingsRow))).scalar_one()
        return OnboardingRecord(row.display_name, row.setup_completed_at)

    async def write_display_name(self, name: str) -> None:
        await self._session.execute(update(SettingsRow).values(display_name=name))
        await self._session.flush()

    async def write_setup_completed(self, at: datetime) -> None:
        await self._session.execute(update(SettingsRow).values(setup_completed_at=at))
        await self._session.flush()
