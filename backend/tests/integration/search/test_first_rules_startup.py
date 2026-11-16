"""002i T006: installs that finished setup before 002i get first rules at start-up (FR-003)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import FakeClock
from hiretitan.preferences.application.service import save_preferences
from hiretitan.preferences.domain.defaults import default_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.infra.repos import RuleSetsRepo
from hiretitan.search_wiring import approve_first_rules_at_start
from hiretitan.setup.infra.settings_repo import SettingsRepo

CLOCK = FakeClock(datetime(2026, 11, 16, 9, 0, tzinfo=UTC))


async def profile_and_preferences(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane"), skills=("Python",)), created_by="manual"
        )
        await save_preferences(
            PreferencesRepo(session),
            CLOCK,
            replace(default_preferences(), target_roles=("Engineer",)),
        )
        await session.commit()


async def finish_setup(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        await SettingsRepo(session).write_setup_completed(CLOCK.now())
        await session.commit()


async def approved(sessions: async_sessionmaker[AsyncSession]) -> object:
    async with sessions() as session:
        return await RuleSetsRepo(session).approved()


async def test_FR003_startup_approves_for_finished_setup(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await profile_and_preferences(sessions)
    await finish_setup(sessions)
    assert await approved(sessions) is None

    await approve_first_rules_at_start(sessions, {})

    rules = await approved(sessions)
    assert rules is not None
    assert rules.approved_by == "auto"  # type: ignore[attr-defined]


async def test_FR003_startup_does_nothing_before_setup(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await profile_and_preferences(sessions)  # setup is not finished

    await approve_first_rules_at_start(sessions, {})

    assert await approved(sessions) is None


async def test_FR003_startup_twice_keeps_one_set(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await profile_and_preferences(sessions)
    await finish_setup(sessions)

    await approve_first_rules_at_start(sessions, {})
    first = await approved(sessions)
    await approve_first_rules_at_start(sessions, {})

    again = await approved(sessions)
    assert first is not None
    assert again is not None
    assert again.id == first.id  # type: ignore[attr-defined]


async def test_FR003_startup_never_fails_the_api(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A fresh install (no settings row, nothing saved) must start without an error."""
    await approve_first_rules_at_start(sessions, {})
    assert await approved(sessions) is None


async def test_FR030_recent_titles_come_from_the_profile_newest_first(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from hiretitan.profile.domain.content import Experience, YearMonth
    from hiretitan.search_wiring import ProfileAndPreferencesSource

    experience = (
        Experience("Old Co", "Junior Developer", start=YearMonth(2019), end=YearMonth(2021)),
        Experience("Now Co", "Backend Engineer", start=YearMonth(2023), current=True),
        Experience("Mid Co", "Software Engineer", start=YearMonth(2021), end=YearMonth(2023)),
        Experience("Older Co", "Intern", start=YearMonth(2018), end=YearMonth(2019)),
    )
    async with sessions() as session:
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane"), skills=("Python",), experience=experience),
            created_by="manual",
        )
        await save_preferences(
            PreferencesRepo(session), CLOCK, replace(default_preferences(), target_roles=("E",))
        )
        await session.commit()
    async with sessions() as session:
        facts = await ProfileAndPreferencesSource(session).read()

    assert facts.source.recent_titles == (
        "Backend Engineer",
        "Software Engineer",
        "Junior Developer",
    )
