"""Database adapter for the ingest use case: one transaction per request."""

from __future__ import annotations

import contextlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.domain.run_state import IllegalTransitionError, RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.application.ingest import FileKind
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

    async def commit(self) -> None:
        await self._session.commit()
