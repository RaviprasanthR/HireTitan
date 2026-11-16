"""Adapters that answer the search module's questions from the profile and preferences.

The search module may not import other features' internals, so this composition-level file
(allowed to see every module) reads the confirmed profile and the saved preferences for it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.config.settings import Settings
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.domain.content import Experience, ProfileContent
from hiretitan.profile.infra.models import ResumeFileRow
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.application.ports import (
    CareerOpsPort,
    DescriptionPort,
    PageFetcherPort,
    ProposalFacts,
    ProposalSource,
)
from hiretitan.search.application.resume_choice import ResumeFacts
from hiretitan.search.application.rules import (
    FirstRulesOutcome,
    RulesService,
    RulesUnavailableError,
)
from hiretitan.search.application.seed import SeedResult, load_seed
from hiretitan.search.domain.cards import ProfileCard, main_skills
from hiretitan.search.domain.proposer import PlaceInput, ProposalInput
from hiretitan.search.domain.resume_choice import offerable
from hiretitan.search.domain.rules_serialization import rules_from_dict
from hiretitan.search.domain.tech_names import TechTable
from hiretitan.search.domain.work_areas import WorkAreaTable
from hiretitan.search.infra.careerops.adapter import CareerOpsAdapter
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.descriptions.fake import FileDescriptions
from hiretitan.search.infra.descriptions.reader import DescriptionReader
from hiretitan.search.infra.repos import CompaniesRepo, RuleSetsRepo
from hiretitan.setup.infra.settings_repo import SettingsRepo


def build_career_ops(settings: Settings) -> CareerOpsPort:
    """The job-board reader: the pinned career-ops, or the file-based fake for end-to-end runs."""
    if settings.career_ops == "fake":
        return FileCareerOps(settings.fake_career_ops_dir)
    return CareerOpsAdapter(career_ops_dir=settings.career_ops_dir, data_dir=settings.data_dir)


def build_descriptions(settings: Settings, pages: PageFetcherPort) -> DescriptionPort:
    """The posting-text reader: the vendors' public APIs and the posting's own page, or the
    file-based fake for end-to-end runs (``HIRETITAN_CAREER_OPS=fake``)."""
    if settings.career_ops == "fake":
        return FileDescriptions(settings.fake_career_ops_dir)
    return DescriptionReader(pages)


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
    sessions: async_sessionmaker[AsyncSession], tech_names: TechTable = ()
) -> Callable[[], Awaitable[ProfileCard | None]]:
    """The profile card the relevance check reads: confirmed profile, saved preferences and the
    approved rules' area and skills.

    The skills come from the person's own approved skill list (which starts from the profile's
    skills and the preferences' key skills, and the person may edit); without approved rules,
    from the profile and preferences directly. The card used to hold only the skills typed in
    Preferences, which are often none (002i, 2026-11-16).
    """

    async def read() -> ProfileCard | None:
        async with sessions() as session:
            try:
                facts = await ProfileAndPreferencesSource(session).read()
            except RulesUnavailableError:
                return None
            approved = await RuleSetsRepo(session).approved()
        source = facts.source
        rules = rules_from_dict(approved.rules) if approved is not None else None
        if rules is not None and rules.stack_keywords:
            skills = main_skills([i.text for i in rules.stack_keywords], (), tech_names)
        else:
            skills = main_skills(source.key_skills, source.profile_skills, tech_names)
        return ProfileCard(
            target_roles=tuple(source.target_roles),
            seniority=tuple(source.seniority_levels),
            years_experience=source.years_experience,
            key_skills=skills,
            preferred_locations=tuple(
                ", ".join(part for part in (p.city, p.country) if part)
                for p in source.preferred_locations
            ),
            work_modes=tuple(sorted(source.work_modes)),
            areas=rules.areas if rules is not None else (),
            recent_titles=source.recent_titles,
        )

    return read


log = logging.getLogger(__name__)


async def approve_first_rules(
    sessions: async_sessionmaker[AsyncSession],
    synonyms: Mapping[str, tuple[str, ...]],
    source: Callable[[AsyncSession], ProposalSource] | None = None,
    work_areas: WorkAreaTable | None = None,
) -> FirstRulesOutcome:
    """Approve the first search rules in a session of their own (002i FR-001)."""
    async with sessions() as session:
        outcome = await RulesService(
            RuleSetsRepo(session),
            (source or ProfileAndPreferencesSource)(session),
            synonyms,
            work_areas,
        ).approve_first()
        await session.commit()
    if outcome == "not_possible":
        log.warning("The first search rules could not be approved (profile or preferences)")
    else:
        log.info("First search rules: %s", outcome)
    return outcome


def first_rules_callback(
    sessions: async_sessionmaker[AsyncSession],
    synonyms: Mapping[str, tuple[str, ...]],
    source: Callable[[AsyncSession], ProposalSource] | None = None,
    work_areas: WorkAreaTable | None = None,
) -> Callable[[], Awaitable[None]]:
    """What finishing setup runs: approve the first rules, nothing else."""

    async def run() -> None:
        await approve_first_rules(sessions, synonyms, source, work_areas)

    return run


async def approve_first_rules_at_start(
    sessions: async_sessionmaker[AsyncSession],
    synonyms: Mapping[str, tuple[str, ...]],
    work_areas: WorkAreaTable | None = None,
) -> None:
    """At API start: an install that finished setup without ever approving rules gets them
    (002i FR-003). Never raises; the API must start either way."""
    try:
        async with sessions() as session:
            finished = await SetupFinishedGate(session).setup_complete()
        if finished:
            await approve_first_rules(sessions, synonyms, work_areas=work_areas)
    except Exception:
        log.exception("Could not approve the first search rules at start-up")


class SetupFinishedGate:
    """``SetupGate``: the first-run setup was completed (the person pressed Finish)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def setup_complete(self) -> bool:
        record = await SettingsRepo(self._session).read_onboarding()
        return record.setup_completed_at is not None


RECENT_TITLES_MAX = 3
RECENT_TITLE_LENGTH = 80


def _recent_titles(profile: ProfileContent) -> tuple[str, ...]:
    """Up to three job titles from the confirmed profile, newest first (a current job first)."""

    def newest(job: Experience) -> tuple[bool, tuple[int, int]]:
        point = job.end or job.start
        return (job.current, (point.year, point.month or 1) if point else (0, 0))

    titles = (
        job.title.strip()[:RECENT_TITLE_LENGTH]
        for job in sorted(profile.experience, key=newest, reverse=True)
        if job.title.strip()
    )
    return tuple(dict.fromkeys(titles))[:RECENT_TITLES_MAX]


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
                recent_titles=_recent_titles(profile),
            ),
            profile_version_id=version.id,
            preferences_saved_at=stored.saved_at,
        )


class SqlResumeLookup:
    """Answers the search module's one question about stored resume files: what is this file called,
    when was it added, and may it be chosen for a job (feature 002f). It reads the profile's own
    table, because ``search`` may not import the profile module.

    The file row is held (``FOR KEY SHARE``) until the transaction ends, so a removal in the
    middle of a mark waits for it instead of leaving the mark to fail on a link to a file that is
    gone, and the two sides take their locks in one order.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, file_id: UUID) -> ResumeFacts | None:
        found = (
            await self._session.execute(
                select(ResumeFileRow)
                .where(ResumeFileRow.id == file_id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if found is None:
            return None
        # "the day it was added" is the UTC day; the file keeps no other date
        added_on = found.created_at.astimezone(UTC).date()
        return ResumeFacts(found.original_name, added_on, offerable(found.parse_status))
