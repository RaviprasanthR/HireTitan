"""Adapters that answer the setup module's questions from the other modules.

The setup module may not import other features directly, so this composition-level file
(allowed to see every module) implements ``SetupFacts`` on top of their repositories.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.domain.run_state import RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.preferences.application.service import get_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.infra.repos import ResumeFilesRepo, ReviewsRepo, VersionsRepo


class RepoFacts:
    """``SetupFacts`` for one database session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resume_uploaded(self) -> bool:
        return bool(await ResumeFilesRepo(self._session).list())

    async def profile_confirmed(self) -> bool:
        return await VersionsRepo(self._session).current() is not None

    async def preferences_saved(self) -> bool:
        return (await get_preferences(PreferencesRepo(self._session))).saved_at is not None

    async def current_open_review_id(self) -> UUID | None:
        review = await ReviewsRepo(self._session).get_open()
        return review.id if review is not None else None

    async def active_run_id(self) -> UUID | None:
        """The newest resume import still in progress: queued, running, paused, or waiting
        for the injection decision. A run waiting for the profile review has an open review."""
        runs = await RunsRepo(self._session).list_by_status(
            RunStatus.queued, RunStatus.running, RunStatus.paused, RunStatus.awaiting_review
        )
        active = [
            r
            for r in runs
            if r.workflow == "profile_ingest"
            and r.state.waiting_for is not WaitingFor.profile_review
        ]
        return active[-1].id if active else None

    async def open_review_id(self, run_id: UUID) -> UUID | None:
        review = await ReviewsRepo(self._session).get_by_run(run_id)
        return review.id if review is not None and review.status == "open" else None
