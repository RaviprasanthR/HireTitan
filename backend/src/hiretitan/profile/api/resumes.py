"""Resume endpoints: upload, paste and list (contracts/rest-api.md, "Resumes and ingestion")."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.storage.port import FileStoragePort
from hiretitan.platform.web.problems import ProblemError
from hiretitan.profile.application.files import ResumeFileNotFoundError, delete_resume_file
from hiretitan.profile.application.ingest import (
    Accepted,
    Inspected,
    JobQueue,
    OpenReviewError,
    ingest_file,
)
from hiretitan.profile.application.manual import ReadingInProgressError
from hiretitan.profile.infra.file_delete_store import SqlFileDeleteStore
from hiretitan.profile.infra.ingest_store import SqlIngestStore
from hiretitan.profile.infra.parsing.sniff import (
    MAX_BYTES,
    CorruptFileError,
    EncryptedFileError,
    FileTooLargeError,
    IntakeError,
    PasswordProtectedOrLegacyDocError,
    TooManyPagesError,
    UnsupportedTypeError,
    sniff,
)
from hiretitan.profile.infra.repos import ResumeFilesRepo, ReviewsRepo

CHUNK: Final = 1024 * 1024

_STATUS_FOR: Final[dict[type[IntakeError], int]] = {
    UnsupportedTypeError: 415,
    PasswordProtectedOrLegacyDocError: 415,
    FileTooLargeError: 413,
    EncryptedFileError: 422,
    CorruptFileError: 422,
    TooManyPagesError: 422,
}


@dataclass(frozen=True, slots=True)
class ProfileApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    storage: FileStoragePort
    queue: JobQueue


class AcceptedOut(BaseModel):
    resume_file_id: UUID
    run_id: UUID


class ResumeFileOut(BaseModel):
    id: UUID
    kind: str
    original_name: str
    size_bytes: int
    page_count: int | None
    parse_status: str
    parse_result: dict[str, Any] | None
    created_at: datetime
    has_open_review: bool
    open_review_id: UUID | None


def _inspect(data: bytes) -> Inspected:
    sniffed = sniff(data)
    return Inspected(sniffed.kind, sniffed.page_count)


async def _read_upload(file: UploadFile) -> bytes:
    """Read the upload in chunks, stopping as soon as it passes the 5 MB limit."""
    parts: list[bytes] = []
    total = 0
    while chunk := await file.read(CHUNK):
        total += len(chunk)
        if total > MAX_BYTES:
            raise FileTooLargeError
        parts.append(chunk)
    return b"".join(parts)


def _problem_for(error: Exception) -> ProblemError:
    if isinstance(error, IntakeError):
        return ProblemError(_STATUS_FOR.get(type(error), 422), str(error))
    if isinstance(error, OpenReviewError):
        return ProblemError(
            409,
            "A profile review is already open. Finish it, or replace it with this resume.",
            open_review_id=str(error.open_review_id),
        )
    raise error


def create_resumes_router(deps: ProfileApiDeps) -> APIRouter:
    router = APIRouter(tags=["resumes"])

    @router.post("/resumes", status_code=202)
    async def upload_resume(
        file: UploadFile,
        discard_open_review: Annotated[bool, Query()] = False,
    ) -> AcceptedOut:
        try:
            data = await _read_upload(file)
            async with deps.sessions() as session:
                accepted: Accepted = await ingest_file(
                    data=data,
                    filename=file.filename,
                    inspect=_inspect,
                    storage=deps.storage,
                    store=SqlIngestStore(session),
                    queue=deps.queue,
                    discard_open_review=discard_open_review,
                )
        except (IntakeError, OpenReviewError) as error:
            raise _problem_for(error) from None
        return AcceptedOut(resume_file_id=accepted.resume_file_id, run_id=accepted.run_id)

    @router.get("/resumes")
    async def list_resumes() -> list[ResumeFileOut]:
        async with deps.sessions() as session:
            files = await ResumeFilesRepo(session).list()
            review: Any = await ReviewsRepo(session).get_open()
        open_file_id = review.resume_file_id if review else None
        open_review_id = review.id if review else None
        return [
            ResumeFileOut(
                id=f.id,
                kind=f.kind,
                original_name=f.original_name,
                size_bytes=f.size_bytes,
                page_count=f.page_count,
                parse_status=f.parse_status,
                parse_result=f.parse_result,
                created_at=f.created_at,
                has_open_review=f.id == open_file_id,
                open_review_id=open_review_id if f.id == open_file_id else None,
            )
            for f in files
        ]

    @router.delete("/resumes/{resume_id}", status_code=204)
    async def delete_resume(resume_id: UUID) -> Response:
        try:
            async with deps.sessions() as session:
                await delete_resume_file(
                    resume_id, store=SqlFileDeleteStore(session), storage=deps.storage
                )
        except ResumeFileNotFoundError:
            raise ProblemError(404, "That resume file was not found.") from None
        except ReadingInProgressError as error:
            raise ProblemError(409, str(error)) from None
        return Response(status_code=204)

    return router
