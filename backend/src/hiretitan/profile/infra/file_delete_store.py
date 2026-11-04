"""Database adapter for deleting one resume file: one transaction per request."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.application.manual import ActiveRun
from hiretitan.profile.infra.ingest_store import SqlIngestStore
from hiretitan.profile.infra.models import ResumeFileRow
from hiretitan.profile.infra.repos import ResumeFilesRepo

_OPEN = (RunStatus.queued, RunStatus.running, RunStatus.paused, RunStatus.awaiting_review)


class SqlFileDeleteStore:
    """Implements ``FileDeleteStore``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._files = ResumeFilesRepo(session)
        self._runs = RunsRepo(session)
        self._ingest = SqlIngestStore(session)

    async def file_sha256(self, file_id: UUID) -> str | None:
        file = await self._files.get(file_id)
        return file.sha256 if file else None

    async def open_runs_for_file(self, file_id: UUID) -> list[ActiveRun]:
        runs = await self._runs.list_by_status(*_OPEN)
        return [
            ActiveRun(r.id, r.state.status is RunStatus.running)
            for r in runs
            if r.subject_id == file_id
        ]

    async def cancel_run(self, run_id: UUID) -> None:
        await self._ingest.cancel_run(run_id)

    async def delete_file(self, file_id: UUID) -> None:
        await self._files.delete(file_id)

    async def hash_in_use(self, sha256: str) -> bool:
        count = await self._session.scalar(
            select(func.count()).select_from(ResumeFileRow).where(ResumeFileRow.sha256 == sha256)
        )
        return bool(count)

    async def commit(self) -> None:
        await self._session.commit()
