"""Adapters that answer the setup module's questions from the other modules.

The setup module may not import other features directly, so this composition-level file
(allowed to see every module) implements ``SetupFacts`` on top of their repositories.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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

    async def open_review_id(self, run_id: UUID) -> UUID | None:
        review = await ReviewsRepo(self._session).get_by_run(run_id)
        return review.id if review is not None and review.status == "open" else None
