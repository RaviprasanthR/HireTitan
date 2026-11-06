"""Adapters that answer the search module's questions from the profile and preferences.

The search module may not import other features' internals, so this composition-level file
(allowed to see every module) reads the confirmed profile and the saved preferences for it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.config.settings import Settings
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.application.ports import CareerOpsPort, ProposalFacts
from hiretitan.search.application.rules import RulesUnavailableError
from hiretitan.search.application.seed import SeedResult, load_seed
from hiretitan.search.domain.cards import ProfileCard
from hiretitan.search.domain.proposer import PlaceInput, ProposalInput
from hiretitan.search.infra.careerops.adapter import CareerOpsAdapter
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.repos import CompaniesRepo
from hiretitan.setup.infra.settings_repo import SettingsRepo


def build_career_ops(settings: Settings) -> CareerOpsPort:
    """The job-board reader: the pinned career-ops, or the file-based fake for end-to-end runs."""
    if settings.career_ops == "fake":
        return FileCareerOps(settings.fake_career_ops_dir)
    return CareerOpsAdapter(career_ops_dir=settings.career_ops_dir, data_dir=settings.data_dir)


async def seed_companies(
    sessions: async_sessionmaker[AsyncSession], path: Path
) -> SeedResult | None:
    """Load the shipped company list at start-up; no file yet (T057) means nothing to load."""
    if not await asyncio.to_thread(path.exists):
        return None
    async with sessions() as session:
        result = await load_seed(CompaniesRepo(session), path)
        await session.commit()
        return result


def profile_card_source(
    sessions: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[ProfileCard | None]]:
    """The profile card the relevance check reads: confirmed profile and saved preferences only."""

    async def read() -> ProfileCard | None:
        async with sessions() as session:
            try:
                facts = await ProfileAndPreferencesSource(session).read()
            except RulesUnavailableError:
                return None
        source = facts.source
        return ProfileCard(
            target_roles=tuple(source.target_roles),
            seniority=tuple(source.seniority_levels),
            years_experience=source.years_experience,
            key_skills=tuple(source.key_skills),
            preferred_locations=tuple(
                ", ".join(part for part in (p.city, p.country) if part)
                for p in source.preferred_locations
            ),
            work_modes=tuple(sorted(source.work_modes)),
        )

    return read


class SetupFinishedGate:
    """``SetupGate``: the first-run setup was completed (the person pressed Finish)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def setup_complete(self) -> bool:
        record = await SettingsRepo(self._session).read_onboarding()
        return record.setup_completed_at is not None


class ProfileAndPreferencesSource:
    """``ProposalSource`` for one database session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self) -> ProposalFacts:
        version = await VersionsRepo(self._session).current()
        if version is None:
            raise RulesUnavailableError("no_confirmed_profile")
        stored = await PreferencesRepo(self._session).read()
        if stored is None or stored.saved_at is None:
            raise RulesUnavailableError("no_preferences")
        prefs = stored.content
        profile = version.content
        mentioned = (*profile.skills, *(t for p in profile.projects for t in p.technologies))
        return ProposalFacts(
            source=ProposalInput(
                target_roles=prefs.target_roles,
                seniority_levels=prefs.seniority_levels,
                years_experience=prefs.years_experience,
                key_skills=prefs.key_skills,
                profile_skills=mentioned,
                preferred_locations=tuple(
                    PlaceInput(p.city, p.country) for p in prefs.preferred_locations
                ),
                blocked_locations=tuple(
                    PlaceInput(p.city, p.country) for p in prefs.blocked_locations
                ),
                work_modes=prefs.work_modes,
            ),
            profile_version_id=version.id,
            preferences_saved_at=stored.saved_at,
        )
