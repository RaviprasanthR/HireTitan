"""T006: the shared test harness runs against a real PostgreSQL 16."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.clock import FakeClock


async def test_real_postgres_16_available(db_session: AsyncSession) -> None:
    version = (await db_session.execute(text("SHOW server_version"))).scalar_one()
    assert str(version).startswith("16")


async def test_session_changes_are_visible_inside_the_test(db_session: AsyncSession) -> None:
    await db_session.execute(text("CREATE TABLE harness_probe (id int)"))
    await db_session.execute(text("INSERT INTO harness_probe VALUES (1)"))
    await db_session.commit()  # commits only the savepoint; the outer transaction rolls back
    count = (await db_session.execute(text("SELECT count(*) FROM harness_probe"))).scalar_one()
    assert count == 1


async def test_session_is_rolled_back_after_each_test(db_session: AsyncSession) -> None:
    # Runs after the test above: its table must be gone.
    exists = (
        await db_session.execute(text("SELECT to_regclass('public.harness_probe') IS NOT NULL"))
    ).scalar_one()
    assert exists is False


def test_tmp_data_dir_is_isolated_and_configured(tmp_data_dir: Path) -> None:
    assert tmp_data_dir.is_dir()
    assert list(tmp_data_dir.iterdir()) == []
    assert os.environ["HIRETITAN_DATA_DIR"] == str(tmp_data_dir)


def test_fake_clock_fixture_is_fixed_utc(fake_clock: FakeClock) -> None:
    assert fake_clock.now() == datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
