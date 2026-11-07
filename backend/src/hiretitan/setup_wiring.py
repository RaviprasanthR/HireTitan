"""Adapters that answer the setup module's questions from the other modules.

The setup module may not import other features directly, so this composition-level file
(allowed to see every module) implements ``SetupFacts`` on top of their repositories.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.domain.run_state import RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.preferences.application.service import get_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.infra.repos import ResumeFilesRepo, ReviewsRepo, VersionsRepo
from hiretitan.search.application import progress as search_progress
from hiretitan.search.application.seed import load_seed
from hiretitan.search.infra.repos import CompaniesRepo, RuleSetsRepo, SearchRunsRepo


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

    async def rules_approved(self) -> bool:
        return await search_progress.rules_approved(RuleSetsRepo(self._session))

    async def searched_once(self) -> bool:
        return await search_progress.searched_once(SearchRunsRepo(self._session))

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


# Tables the app owns outside the ``app`` schema, found by name so new ones are covered too.
_WIPE_TABLES = r"""
SELECT quote_ident(table_schema) || '.' || quote_ident(table_name)
FROM information_schema.tables
WHERE table_type = 'BASE TABLE' AND (
    (table_schema = 'app' AND table_name <> 'alembic_version')
    OR (table_schema = 'lg' AND table_name <> 'checkpoint_migrations')
    OR (table_schema = 'public' AND table_name LIKE 'procrastinate\_%'
        AND table_name !~ '(version|migration)')
)
ORDER BY 1
"""


class SqlDeleteAllStore:
    """``DeleteAllStore`` over every module's tables (a composition-level adapter, because it
    spans features, the job queue and the checkpoint store)."""

    def __init__(self, session: AsyncSession, company_seed: Path | None = None) -> None:
        self._session = session
        self._company_seed = company_seed

    async def cancel_open_runs(self) -> None:
        runs = RunsRepo(self._session)
        for run in await runs.list_by_status(
            RunStatus.queued, RunStatus.running, RunStatus.paused, RunStatus.awaiting_review
        ):
            if run.state.status is RunStatus.queued:  # a queued run must start before it ends
                await runs.transition(run.id, RunStatus.running)
            await runs.transition(run.id, RunStatus.cancelled)
        await self._session.commit()

    async def wipe_and_reseed(self) -> None:
        tables = (await self._session.execute(text(_WIPE_TABLES))).scalars().all()
        await self._session.execute(
            text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
        )
        # What a fresh install has (migrations 0005 and 0006).
        await self._session.execute(text("INSERT INTO app.settings DEFAULT VALUES"))
        await self._session.execute(
            text("INSERT INTO app.provider_status (provider, status) VALUES ('openai', 'unknown')")
        )
        # The shipped company list, as a fresh install has it (FR-041).
        if self._company_seed is not None and await asyncio.to_thread(self._company_seed.exists):
            await load_seed(CompaniesRepo(self._session), self._company_seed)
        await self._session.commit()
