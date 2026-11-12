"""Interview tracking use cases (feature 002e): what the person recorded about a pipeline job.

Contacts, rounds, questions and feedback are the person's own notes and are never sent to an AI
(FR-010), so nothing under ``search/workflow``, ``prompts`` or ``platform/llm`` may import this
module (an import-linter contract checks it).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from hiretitan.search.domain.contacts import ContactFields, FieldIssue
from hiretitan.search.domain.interviews import (
    RoundSummary,
    can_add_round,
    check_contact,
    check_source,
    status_summary,
)

PIPELINE_STATES = ("applied", "inquired")


class JobNotFoundError(LookupError):
    """The job does not exist (or was deleted)."""


class StoredJob(Protocol):
    id: UUID
    state: str


class JobsLookup(Protocol):
    async def get(self, job_id: UUID) -> StoredJob | None: ...


class StoredDetails(Protocol):
    contact_name: str | None
    contact_role: str | None
    contact_email: str | None
    contact_phone: str | None
    contact_linkedin: str | None
    source: str | None
    firm_name: str | None


class StoredRound(Protocol):
    id: UUID
    number: int
    kind: str
    state: str
    scheduled_at: datetime | None
    interviewers: str | None
    feedback: str | None


class StoredQuestion(Protocol):
    id: UUID
    position: int
    question: str
    answer: str | None


class StoredRoundWithQuestions(Protocol):
    @property
    def round(self) -> StoredRound: ...

    @property
    def questions(self) -> Sequence[StoredQuestion]: ...


class StoredInterview(Protocol):
    @property
    def details(self) -> StoredDetails | None: ...

    @property
    def rounds(self) -> Sequence[StoredRoundWithQuestions]: ...


class InterviewsStore(Protocol):
    async def details(self, job_id: UUID) -> StoredInterview: ...


@dataclass(frozen=True, slots=True)
class ContactView:
    name: str
    role: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None


@dataclass(frozen=True, slots=True)
class SourceView:
    kind: str
    firm_name: str | None


@dataclass(frozen=True, slots=True)
class QuestionView:
    id: UUID
    position: int
    question: str
    answer: str | None


@dataclass(frozen=True, slots=True)
class RoundView:
    id: UUID
    number: int
    kind: str
    state: str
    scheduled_at: datetime | None
    interviewers: str | None
    feedback: str | None
    questions: list[QuestionView]


@dataclass(frozen=True, slots=True)
class StatusView:
    state: str
    round: int | None


@dataclass(frozen=True, slots=True)
class InterviewView:
    job_id: UUID
    can_edit: bool
    can_add_round: bool
    contact: ContactView | None
    source: SourceView | None
    rounds: list[RoundView]
    status: StatusView


async def read_interview(
    jobs: JobsLookup, interviews: InterviewsStore, job_id: UUID
) -> InterviewView:
    """Everything recorded for the job, with the status the pipeline list shows (FR-007)."""
    job = await jobs.get(job_id)
    if job is None or job.state == "deleted":
        raise JobNotFoundError(str(job_id))
    stored = await interviews.details(job_id)
    details = stored.details

    rounds = [
        RoundView(
            id=item.round.id,
            number=item.round.number,
            kind=item.round.kind,
            state=item.round.state,
            scheduled_at=item.round.scheduled_at,
            interviewers=item.round.interviewers,
            feedback=item.round.feedback,
            questions=[
                QuestionView(q.id, q.position, q.question, q.answer) for q in item.questions
            ],
        )
        for item in stored.rounds
    ]
    state, number = status_summary(job.state, [RoundSummary(r.number, r.state) for r in rounds])
    in_pipeline = job.state in PIPELINE_STATES

    contact = (
        ContactView(
            name=details.contact_name,
            role=details.contact_role,
            email=details.contact_email,
            phone=details.contact_phone,
            linkedin_url=details.contact_linkedin,
        )
        if details is not None and details.contact_name is not None
        else None
    )
    source = (
        SourceView(kind=details.source, firm_name=details.firm_name)
        if details is not None and details.source is not None
        else None
    )
    return InterviewView(
        job_id=job_id,
        can_edit=in_pipeline,
        can_add_round=in_pipeline and can_add_round(r.state for r in rounds),
        contact=contact,
        source=source,
        rounds=rounds,
        status=StatusView(state=state, round=number),
    )


class NotInPipelineError(ValueError):
    """The job is not applied or inquired, so nothing new can be recorded for it (research R6)."""


class InterviewInputError(ValueError):
    """Typed details failed their checks; nothing was saved."""

    def __init__(self, errors: list[FieldIssue]) -> None:
        super().__init__(" ".join(e.message for e in errors))
        self.errors = errors


class InterviewsWriter(Protocol):
    async def upsert_contact(self, job_id: UUID, fields: ContactFields) -> None: ...

    async def clear_contact(self, job_id: UUID) -> None: ...

    async def set_source(self, job_id: UUID, kind: str | None, firm_name: str | None) -> None: ...


async def _writable_job(jobs: JobsLookup, job_id: UUID) -> StoredJob:
    job = await jobs.get(job_id)
    if job is None or job.state == "deleted":
        raise JobNotFoundError(str(job_id))
    if job.state not in PIPELINE_STATES:
        raise NotInPipelineError(
            "This job is not in your pipeline. Mark it applied or inquired first."
        )
    return job


async def save_contact(
    jobs: JobsLookup,
    store: InterviewsWriter,
    job_id: UUID,
    *,
    name: str | None,
    role: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    linkedin_url: str | None = None,
) -> None:
    """Replace the point of contact; email, phone and link are checked (FR-002)."""
    await _writable_job(jobs, job_id)
    fields, issues = check_contact(
        name=name, role=role, email=email, phone=phone, linkedin_url=linkedin_url
    )
    if fields is None:
        raise InterviewInputError(issues)
    await store.upsert_contact(job_id, fields)


async def remove_contact(jobs: JobsLookup, store: InterviewsWriter, job_id: UUID) -> None:
    await _writable_job(jobs, job_id)
    await store.clear_contact(job_id)


async def save_source(
    jobs: JobsLookup,
    store: InterviewsWriter,
    job_id: UUID,
    *,
    kind: str | None,
    firm_name: str | None = None,
) -> None:
    """How the job came: direct, through a hiring firm (with its name) or not set (FR-003)."""
    await _writable_job(jobs, job_id)
    checked, issues = check_source(kind, firm_name)
    if checked is None:
        raise InterviewInputError(issues)
    await store.set_source(job_id, checked[0], checked[1])
