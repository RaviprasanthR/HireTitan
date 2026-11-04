"""T071: migration 0009 and the onboarding store (FR-039, FR-040)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.setup.application.onboarding import (
    SetupNotReady,
    complete_setup,
    get_onboarding_record,
    set_display_name,
)
from hiretitan.setup.infra.settings_repo import SettingsRepo


def test_fresh_install_starts_without_name_or_completion(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    command.upgrade(make_alembic_config(fresh_database_url), "head")
    engine = create_engine(fresh_database_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT display_name, setup_completed_at FROM app.settings")
            ).one()
        assert tuple(row) == (None, None)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("profile", "preferences", "expect_complete"),
    [(True, True, True), (True, False, False), (False, True, False), (False, False, False)],
)
def test_FR040_existing_install_counts_as_set_up(
    fresh_database_url: str,
    make_alembic_config: Callable[[str], Config],
    profile: bool,
    preferences: bool,
    expect_complete: bool,
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0008")
    engine = create_engine(fresh_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO app.profiles (id) VALUES (gen_random_uuid())"))
            if profile:
                conn.execute(
                    text(
                        "INSERT INTO app.profile_versions (id, profile_id, number, content, created_by)"
                        " SELECT gen_random_uuid(), id, 1, '{}', 'manual' FROM app.profiles"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE app.profiles SET current_version_id ="
                        " (SELECT id FROM app.profile_versions LIMIT 1)"
                    )
                )
            if preferences:
                conn.execute(
                    text("INSERT INTO app.preferences (content, saved_at) VALUES ('{}', now())")
                )
        command.upgrade(cfg, "0009")
        with engine.connect() as conn:
            done = conn.execute(text("SELECT setup_completed_at FROM app.settings")).scalar()
        assert (done is not None) is expect_complete
    finally:
        engine.dispose()


async def test_FR039_name_is_stored_and_trimmed(db_session: AsyncSession) -> None:
    store = SettingsRepo(db_session)
    assert (await get_onboarding_record(store)).display_name is None
    await set_display_name(store, "  Jane  ")
    assert (await get_onboarding_record(store)).display_name == "Jane"


@pytest.mark.parametrize("bad", ["", "   ", "x" * 121])
async def test_FR039_name_must_be_1_to_120_characters(db_session: AsyncSession, bad: str) -> None:
    with pytest.raises(ValueError):
        await set_display_name(SettingsRepo(db_session), bad)


async def test_db_rejects_an_empty_name(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(text("UPDATE app.settings SET display_name = ''"))


async def test_complete_setup_needs_a_profile_and_preferences(db_session: AsyncSession) -> None:
    store = SettingsRepo(db_session)
    now = datetime(2026, 11, 4, 9, tzinfo=UTC)
    with pytest.raises(SetupNotReady):
        await complete_setup(store, now, profile_confirmed=False, preferences_saved=True)
    with pytest.raises(SetupNotReady):
        await complete_setup(store, now, profile_confirmed=True, preferences_saved=False)
    assert (await get_onboarding_record(store)).setup_completed_at is None

    await complete_setup(store, now, profile_confirmed=True, preferences_saved=True)
    assert (await get_onboarding_record(store)).setup_completed_at == now


async def test_completing_twice_keeps_the_first_time(db_session: AsyncSession) -> None:
    store = SettingsRepo(db_session)
    first = datetime(2026, 11, 4, 9, tzinfo=UTC)
    await complete_setup(store, first, profile_confirmed=True, preferences_saved=True)
    await complete_setup(
        store, datetime(2026, 11, 5, tzinfo=UTC), profile_confirmed=True, preferences_saved=True
    )
    assert (await get_onboarding_record(store)).setup_completed_at == first
