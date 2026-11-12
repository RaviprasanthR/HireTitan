"""T021: the settings singleton (the person's name and the setup state)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.setup.infra.settings_repo import SettingsRepo


async def test_a_new_install_has_no_name_and_no_completed_setup(db_session: AsyncSession) -> None:
    record = await SettingsRepo(db_session).read_onboarding()

    assert (record.display_name, record.setup_completed_at) == (None, None)


async def test_name_and_completion_are_saved(db_session: AsyncSession) -> None:
    repo = SettingsRepo(db_session)
    when = datetime(2026, 11, 12, 9, tzinfo=UTC)

    await repo.write_display_name("Jane")
    await repo.write_setup_completed(when)

    record = await repo.read_onboarding()
    assert (record.display_name, record.setup_completed_at) == ("Jane", when)


async def test_settings_is_a_singleton(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(text("INSERT INTO app.settings (id) VALUES (false)"))
