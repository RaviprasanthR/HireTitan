"""The pipeline's one settings row: the resume the person chose last (feature 002f).

Kept apart from the other repositories, like the interview notes, so an import-linter contract can
forbid every AI path from importing it: the person's choices never reach a model (FR-013).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.infra.models import PipelineSettingsRow

ROW_ID = 1


class PipelineSettingsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def last_choice(self) -> UUID | None:
        """The resume chosen the last time a job was marked; ``None`` for none, for a person who
        never chose, and when that file has since been removed (the database clears the link)."""
        return (
            await self._session.execute(
                select(PipelineSettingsRow.last_resume_file_id).where(
                    PipelineSettingsRow.id == ROW_ID
                )
            )
        ).scalar_one_or_none()

    async def set_last_choice(self, file_id: UUID | None) -> None:
        """Remember a choice, including an explicit ``None`` (a mark made without a resume)."""
        stmt = pg_insert(PipelineSettingsRow).values(id=ROW_ID, last_resume_file_id=file_id)
        await self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=[PipelineSettingsRow.id],
                set_={"last_resume_file_id": stmt.excluded.last_resume_file_id},
            )
        )
        await self._session.flush()

    async def forget(self, file_id: UUID) -> None:
        """The last choice goes back to none if it was this file."""
        await self._session.execute(
            update(PipelineSettingsRow)
            .where(PipelineSettingsRow.last_resume_file_id == file_id)
            .values(last_resume_file_id=None)
        )
        await self._session.flush()
