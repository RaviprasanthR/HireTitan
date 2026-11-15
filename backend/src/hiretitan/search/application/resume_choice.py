"""The resume a person used for a pipeline job (feature 002f): choose it, clear it, record it when
a job is marked applied or inquired.

The choice is the person's own record, never an AI input (FR-013), so nothing under
``search/workflow``, ``prompts`` or ``platform/llm`` may import this module (an import-linter
contract checks it). The stored files belong to the profile module, which ``search`` may not
import: ``ResumeLookup`` is the one question it asks, answered in ``search_wiring.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from hiretitan.search.application.interviews import (
    InterviewInputError,
    JobsLookup,
    writable_job,
)
from hiretitan.search.domain.contacts import FieldIssue
from hiretitan.search.domain.resume_choice import ResumeChoice, choice_from


@dataclass(frozen=True, slots=True)
class ResumeFacts:
    """What the job needs to know about a stored resume file: its name, the day it was added,
    and whether it may be chosen (a file rejected as "not a resume" may not, FR-012)."""

    name: str
    added_on: date
    offerable: bool


class ResumeLookup(Protocol):
    async def get(self, file_id: UUID) -> ResumeFacts | None: ...


class ResumeWriter(Protocol):
    async def lock_job(self, job_id: UUID) -> None: ...

    async def set_resume(self, job_id: UUID, file_id: UUID, name: str, added_on: date) -> None: ...

    async def clear_resume(self, job_id: UUID) -> None: ...


class LastChoiceWriter(Protocol):
    async def set_last_choice(self, file_id: UUID | None) -> None: ...


async def _offerable_file(lookup: ResumeLookup, file_id: UUID) -> ResumeFacts:
    facts = await lookup.get(file_id)
    if facts is None or not facts.offerable:
        raise InterviewInputError(
            [FieldIssue("resume_file_id", "Choose one of your stored resume files.")]
        )
    return facts


async def _assign(
    lookup: ResumeLookup, store: ResumeWriter, job_id: UUID, file_id: UUID
) -> ResumeChoice:
    facts = await _offerable_file(lookup, file_id)
    await store.set_resume(job_id, file_id, facts.name, facts.added_on)
    return choice_from(file_id, facts.name, facts.added_on)


async def choose_for_job(
    jobs: JobsLookup, lookup: ResumeLookup, store: ResumeWriter, job_id: UUID, file_id: UUID
) -> ResumeChoice:
    """Set the job's resume to a stored file: the link, and a copy of its name and day."""
    await store.lock_job(job_id)  # so a delete or merge cannot slip in between check and write
    await writable_job(jobs, job_id)
    return await _assign(lookup, store, job_id, file_id)


async def clear_for_job(jobs: JobsLookup, store: ResumeWriter, job_id: UUID) -> None:
    """Forget the job's resume, or the note a removed file left behind."""
    await store.lock_job(job_id)
    await writable_job(jobs, job_id)
    await store.clear_resume(job_id)


async def record_on_mark(
    jobs: JobsLookup,
    lookup: ResumeLookup,
    store: ResumeWriter,
    settings: LastChoiceWriter,
    job_id: UUID,
    *,
    provided: bool,
    file_id: UUID | None,
) -> None:
    """Called in the same transaction as marking a job applied or inquired.

    ``provided`` is whether the request carried a ``resume_file_id`` at all. Absent: the job
    keeps the resume it has (inquired to applied, FR-003) and the last choice is untouched, so a
    one-click mark behaves as before (FR-002). Present: the job's resume is set to that file, or
    cleared for ``None``, and the person's last choice becomes it (FR-014).
    """
    if not provided:
        return
    await store.lock_job(job_id)
    await writable_job(jobs, job_id)
    if file_id is None:
        await store.clear_resume(job_id)
    else:
        await _assign(lookup, store, job_id, file_id)
    await settings.set_last_choice(file_id)
