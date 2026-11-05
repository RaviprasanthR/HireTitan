"""T053: preferences persistence and application (FR-023 to FR-026, US2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import FakeClock
from hiretitan.platform.untrusted.mask_contacts import mask_contacts
from hiretitan.preferences.application.service import (
    PreferencesInvalid,
    get_default_country,
    get_preferences,
    get_suggestions,
    save_preferences,
)
from hiretitan.preferences.domain.defaults import default_preferences
from hiretitan.preferences.domain.model import Pay, Place, Preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.domain.content import Contact, Experience, ProfileContent, YearMonth
from hiretitan.profile.infra.repos import VersionsRepo


def filled() -> Preferences:
    return replace(
        default_preferences(),
        target_roles=("Backend Engineer", "Platform Engineer"),
        seniority_levels=("senior",),
        years_experience=Decimal("6.5"),
        key_skills=("Python", "PostgreSQL"),
        preferred_locations=(Place("Pune", "IN"), Place(None, "DE")),
        default_country="DE",
        work_modes=frozenset({"remote", "hybrid"}),
        willing_to_relocate=True,
        blocked_locations=(Place("Atlantis", "GB"),),
        job_types=frozenset({"full_time", "contract"}),
        pay=Pay("EUR", Decimal(60_000), Decimal(80_000), "total"),
        notice_period_days=None,
        earliest_start_date=date(2027, 2, 1),
        preferred_companies=("Acme",),
        avoided_companies=("Initech",),
    )


async def make_profile(session: AsyncSession) -> None:
    old = Experience(
        employer="Old Co", title="Junior Dev", start=YearMonth(2015, 1), end=YearMonth(2018, 6)
    )
    new = Experience(
        employer="Acme", title="Staff Engineer", start=YearMonth(2019, 3), current=True
    )
    content = ProfileContent(
        contact=Contact(name="Jane Example"),
        experience=(old, new),
        skills=("Python", "Go", "Kubernetes"),
    )
    await VersionsRepo(session).create_version(content, created_by="manual")


async def test_US2_AS1_defaults_when_never_saved(db_session: AsyncSession) -> None:
    stored = await get_preferences(PreferencesRepo(db_session))
    assert stored.content == default_preferences()
    assert stored.saved_at is None


async def test_US2_AS2_persists_across_sessions(
    sessions: async_sessionmaker[AsyncSession], fake_clock: FakeClock
) -> None:
    async with sessions() as first:
        saved_at = await save_preferences(PreferencesRepo(first), fake_clock, filled())
        await first.commit()
    assert saved_at == fake_clock.now()
    async with sessions() as second:
        stored = await get_preferences(PreferencesRepo(second))
    assert stored.content == filled()
    assert stored.saved_at == saved_at


async def test_save_replaces_the_single_row(
    db_session: AsyncSession, fake_clock: FakeClock
) -> None:
    repo = PreferencesRepo(db_session)
    await save_preferences(repo, fake_clock, filled())
    await save_preferences(repo, fake_clock, replace(filled(), target_roles=("Data Engineer",)))
    assert (await get_preferences(repo)).content.target_roles == ("Data Engineer",)
    count = await db_session.scalar(text("SELECT count(*) FROM app.preferences"))
    assert count == 1


async def test_invalid_preferences_are_not_saved(
    db_session: AsyncSession, fake_clock: FakeClock
) -> None:
    repo = PreferencesRepo(db_session)
    with pytest.raises(PreferencesInvalid) as caught:
        await save_preferences(repo, fake_clock, default_preferences())
    assert [e.path for e in caught.value.errors] == ["target_roles"]
    assert (await get_preferences(repo)).saved_at is None


async def test_db_allows_only_one_row(db_session: AsyncSession) -> None:
    await db_session.execute(text("INSERT INTO app.preferences (content) VALUES ('{}')"))
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO app.preferences (singleton, content) VALUES (false, '{}')")
        )


async def test_US2_AS3_suggestions_from_profile_not_auto_added(
    db_session: AsyncSession, fake_clock: FakeClock
) -> None:
    repo = PreferencesRepo(db_session)
    await make_profile(db_session)
    chosen = replace(
        default_preferences(), target_roles=("Backend Engineer",), key_skills=("python",)
    )
    await save_preferences(repo, fake_clock, chosen)

    suggestions = await get_suggestions(repo, VersionsRepo(db_session))

    assert suggestions.target_roles == ("Staff Engineer",)  # the most recent title
    assert suggestions.key_skills == ("Go", "Kubernetes")  # "Python" is already chosen
    assert (await get_preferences(repo)).content == chosen  # nothing was added by itself


async def test_suggestions_skip_a_role_already_chosen(db_session: AsyncSession) -> None:
    await make_profile(db_session)
    repo = PreferencesRepo(db_session)
    await save_preferences(
        repo, FakeClock(), replace(default_preferences(), target_roles=("staff engineer",))
    )
    assert (await get_suggestions(repo, VersionsRepo(db_session))).target_roles == ()


async def test_FR026_save_without_profile(db_session: AsyncSession, fake_clock: FakeClock) -> None:
    repo = PreferencesRepo(db_session)
    await save_preferences(repo, fake_clock, filled())
    suggestions = await get_suggestions(repo, VersionsRepo(db_session))
    assert suggestions.target_roles == ()
    assert suggestions.key_skills == ()


async def test_default_country_feeds_contact_masking(
    db_session: AsyncSession, fake_clock: FakeClock
) -> None:
    repo = PreferencesRepo(db_session)
    assert await get_default_country(repo) == "IN"
    await save_preferences(repo, fake_clock, replace(filled(), default_country="GB"))
    region = await get_default_country(repo)
    assert region == "GB"
    masked = mask_contacts("Call me on 020 7946 0958 today", default_region=region)
    assert "7946" not in masked.text
