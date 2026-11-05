"""Deleting one stored resume file (FR-034, US4 scenario 1).

The file's row goes, and with it any open review. Profile versions made from it keep their
content and AI provenance and are marked ``source_deleted``. Its runs are cancelled first; a run
that is executing right now is left alone and the user is asked to try again. The bytes on disk
go only when no other row still points at the same content hash.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from hiretitan.profile.application.manual import ActiveRun, ReadingInProgressError


class ResumeFileNotFoundError(LookupError):
    """No resume file with that id."""


class FileDeleteStore(Protocol):
    """One database transaction."""

    async def file_sha256(self, file_id: UUID) -> str | None: ...

    async def open_runs_for_file(self, file_id: UUID) -> list[ActiveRun]:
        """Runs for this file that have not ended."""
        ...

    async def cancel_run(self, run_id: UUID) -> None: ...

    async def delete_file(self, file_id: UUID) -> None:
        """Delete the row, its reviews, and mark versions made from it."""
        ...

    async def hash_in_use(self, sha256: str) -> bool: ...

    async def commit(self) -> None: ...


class BlobStorage(Protocol):
    def delete(self, sha256: str) -> None: ...


async def delete_resume_file(
    file_id: UUID, *, store: FileDeleteStore, storage: BlobStorage
) -> None:
    sha256 = await store.file_sha256(file_id)
    if sha256 is None:
        raise ResumeFileNotFoundError(file_id)
    runs = await store.open_runs_for_file(file_id)
    for run in runs:
        if run.running:
            raise ReadingInProgressError(run.id)
    for run in runs:
        await store.cancel_run(run.id)
    await store.delete_file(file_id)
    still_used = await store.hash_in_use(sha256)
    await store.commit()
    # Delete the bytes only after the database change is saved, so a failure here leaves at
    # worst an unreferenced file, never a row pointing at nothing.
    if not still_used:
        storage.delete(sha256)
