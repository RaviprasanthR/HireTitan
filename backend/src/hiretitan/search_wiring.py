"""Adapters that answer the search module's questions from the profile and preferences.

The search module may not import other features' internals, so this composition-level file
(allowed to see every module) reads the confirmed profile and the saved preferences for it.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.application.ports import ProposalFacts
from hiretitan.search.application.rules import RulesUnavailableError
from hiretitan.search.domain.proposer import PlaceInput, ProposalInput


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
