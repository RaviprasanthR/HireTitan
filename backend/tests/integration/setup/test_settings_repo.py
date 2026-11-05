"""T021: the settings singleton (budget cap)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.setup.application.settings import get_budget_cap
from hiretitan.setup.infra.settings_repo import SettingsRepo


async def test_FR031_default_cap_25_usd(db_session: AsyncSession) -> None:
    assert await SettingsRepo(db_session).read_budget_cap() == Decimal("25.00")
    assert await get_budget_cap(SettingsRepo(db_session)) == Decimal("25.00")


async def test_cap_can_be_changed(db_session: AsyncSession) -> None:
    repo = SettingsRepo(db_session)
    await repo.write_budget_cap(Decimal("10.50"))
    assert await repo.read_budget_cap() == Decimal("10.50")


async def test_db_rejects_negative_cap(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await SettingsRepo(db_session).write_budget_cap(Decimal("-1"))


async def test_settings_is_a_singleton(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(text("INSERT INTO app.settings (id) VALUES (false)"))
