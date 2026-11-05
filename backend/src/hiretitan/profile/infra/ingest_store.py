"""Database adapter for the ingest use case: one transaction per request."""

from __future__ import annotations

import contextlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.domain.run_state import (
    IllegalTransitionError,
    RunStatus,
    WaitingFor,
)
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.application.ingest import FileKind
from hiretitan.profile.application.manual import ActiveRun
from hiretitan.profile.infra.repos import ResumeFilesRepo, ReviewsRepo

WORKFLOW = "profile_ingest"


class SqlIngestStore:
    """Implements ``IngestStore``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._files = ResumeFilesRepo(session)
        self._reviews = ReviewsRepo(session)
        self._runs = RunsRepo(session)

    async def open_review_id(self) -> UUID | None:
        review = await self._reviews.get_open()
        return review.id if review else None

    async def discard_open_review(self, review_id: UUID) -> None:
        review = await self._reviews.get(review_id)
        if review is None:
            return
        await self._reviews.set_status(review_id, "discarded")
        # If the run already ended there is nothing left to cancel.
        with contextlib.suppress(IllegalTransitionError):
            await self._runs.transition(review.run_id, RunStatus.cancelled)

    async def add_file(
        self,
        *,
        kind: FileKind,
        original_name: str,
        size_bytes: int,
        sha256: str,
        page_count: int | None,
    ) -> UUID:
        file = await self._files.create(
            kind=kind,
            original_name=original_name,
            size_bytes=size_bytes,
            sha256=sha256,
            page_count=page_count,
        )
        return file.id

    async def start_run(self, resume_file_id: UUID) -> UUID:
        run = await self._runs.create(WORKFLOW, subject_id=resume_file_id)
        return run.id

    async def active_runs(self) -> list[ActiveRun]:
        """Imports still in progress, oldest first: queued, running, paused, or waiting for
        the injection decision. A run waiting for the profile review has an open review."""
        runs = await self._runs.list_by_status(
            RunStatus.queued, RunStatus.running, RunStatus.paused, RunStatus.awaiting_review
        )
        return [
            ActiveRun(r.id, r.state.status is RunStatus.running)
            for r in runs
            if r.workflow == WORKFLOW and r.state.waiting_for is not WaitingFor.profile_review
        ]

    async def cancel_run(self, run_id: UUID) -> None:
        run = await self._runs.get(run_id)
        if run is None:
            return
        if run.state.status is RunStatus.queued:  # a queued run must start before it can end
            await self._runs.transition(run_id, RunStatus.running)
        await self._runs.transition(run_id, RunStatus.cancelled)

    async def start_manual_run(self) -> UUID:
        run = await self._runs.create(WORKFLOW)  # no subject: no resume file
        return run.id

    async def commit(self) -> None:
        await self._session.commit()
