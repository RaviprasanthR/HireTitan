"""Repository for the settings singleton, and the budget-cap provider for the AI guard."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.setup.application.onboarding import OnboardingRecord
from hiretitan.setup.application.settings import get_budget_cap
from hiretitan.setup.infra.models import SettingsRow


class SettingsRepo:
    """Implements ``SettingsStore``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_budget_cap(self) -> Decimal:
        cap = await self._session.scalar(select(SettingsRow.budget_cap_usd))
        return Decimal("25.00") if cap is None else Decimal(cap)

    async def write_budget_cap(self, cap: Decimal) -> None:
        await self._session.execute(update(SettingsRow).values(budget_cap_usd=cap))
        await self._session.flush()

    async def read_onboarding(self) -> OnboardingRecord:
        row = (await self._session.execute(select(SettingsRow))).scalar_one()
        return OnboardingRecord(row.display_name, row.setup_completed_at)

    async def write_display_name(self, name: str) -> None:
        await self._session.execute(update(SettingsRow).values(display_name=name))
        await self._session.flush()

    async def write_setup_completed(self, at: datetime) -> None:
        await self._session.execute(update(SettingsRow).values(setup_completed_at=at))
        await self._session.flush()


def budget_cap_provider(
    sessions: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[Decimal]]:
    """The injected cap source for the budget guard (platform never imports setup)."""

    async def provider() -> Decimal:
        async with sessions() as session:
            return await get_budget_cap(SettingsRepo(session))

    return provider
