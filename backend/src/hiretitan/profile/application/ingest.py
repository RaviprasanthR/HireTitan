"""Accepting a resume: upload or pasted text (FR-001, FR-002, FR-003).

The use case checks the input, refuses while a review is open (unless told to replace it),
keeps the original bytes unchanged, records the file and a queued ``profile_ingest`` run, and
only then hands the run to the job queue. Everything it needs from outside is a port, so the
database and file system stay in ``infra``.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Final, Literal, Protocol
from uuid import UUID

MIN_PASTED_CHARS: Final = 200
MAX_PASTED_CHARS: Final = 60_000
PASTED_NAME: Final = "pasted text"
MAX_NAME_CHARS: Final = 255

FileKind = Literal["upload_pdf", "upload_docx", "pasted_text"]


@dataclass(frozen=True, slots=True)
class Inspected:
    kind: Literal["pdf", "docx"]
    page_count: int | None


@dataclass(frozen=True, slots=True)
class Accepted:
    resume_file_id: UUID
    run_id: UUID


class OpenReviewError(Exception):
    """A profile review is already open; the user must finish it or replace it."""

    def __init__(self, open_review_id: UUID) -> None:
        super().__init__("A profile review is already open")
        self.open_review_id = open_review_id


class Inspector(Protocol):
    def __call__(self, data: bytes) -> Inspected:
        """Identify and check an uploaded file; raises a user-facing error if unacceptable."""
        ...


class Storage(Protocol):
    def put(self, data: bytes) -> str: ...


class IngestStore(Protocol):
    """One database transaction."""

    async def open_review_id(self) -> UUID | None: ...

    async def discard_open_review(self, review_id: UUID) -> None:
        """Mark the review discarded and cancel its run."""
        ...

    async def add_file(
        self,
        *,
        kind: FileKind,
        original_name: str,
        size_bytes: int,
        sha256: str,
        page_count: int | None,
    ) -> UUID: ...

    async def start_run(self, resume_file_id: UUID) -> UUID: ...

    async def commit(self) -> None: ...


class JobQueue(Protocol):
    async def enqueue(self, run_id: UUID, resume: object = None) -> None: ...


def display_name(filename: str | None) -> str:
    """The base name only (browsers may send a full path), at most 255 characters."""
    name = posixpath.basename((filename or "").replace("\\", "/")).strip()
    return (name or "resume")[:MAX_NAME_CHARS]


async def _accept(
    *,
    store: IngestStore,
    queue: JobQueue,
    kind: FileKind,
    original_name: str,
    size_bytes: int,
    sha256: str,
    page_count: int | None,
    discard_open_review: bool,
) -> Accepted:
    open_id = await store.open_review_id()
    if open_id is not None:
        if not discard_open_review:
            raise OpenReviewError(open_id)
        await store.discard_open_review(open_id)
    file_id = await store.add_file(
        kind=kind,
        original_name=original_name,
        size_bytes=size_bytes,
        sha256=sha256,
        page_count=page_count,
    )
    run_id = await store.start_run(file_id)
    await store.commit()
    await queue.enqueue(run_id)
    return Accepted(file_id, run_id)


async def ingest_file(
    *,
    data: bytes,
    filename: str | None,
    inspect: Inspector,
    storage: Storage,
    store: IngestStore,
    queue: JobQueue,
    discard_open_review: bool = False,
) -> Accepted:
    inspected = inspect(data)  # raises before anything is stored
    open_id = await store.open_review_id()
    if open_id is not None and not discard_open_review:
        raise OpenReviewError(open_id)  # checked before the file is written to disk
    sha256 = storage.put(data)
    return await _accept(
        store=store,
        queue=queue,
        kind="upload_pdf" if inspected.kind == "pdf" else "upload_docx",
        original_name=display_name(filename),
        size_bytes=len(data),
        sha256=sha256,
        page_count=inspected.page_count,
        discard_open_review=discard_open_review,
    )


async def ingest_text(
    *,
    text: str,
    storage: Storage,
    store: IngestStore,
    queue: JobQueue,
    discard_open_review: bool = False,
) -> Accepted:
    data = text.encode("utf-8")
    open_id = await store.open_review_id()
    if open_id is not None and not discard_open_review:
        raise OpenReviewError(open_id)
    sha256 = storage.put(data)
    return await _accept(
        store=store,
        queue=queue,
        kind="pasted_text",
        original_name=PASTED_NAME,
        size_bytes=len(data),
        sha256=sha256,
        page_count=None,
        discard_open_review=discard_open_review,
    )
