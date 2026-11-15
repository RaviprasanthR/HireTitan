"""Interview tracking use cases (feature 002e): what the person recorded about a pipeline job.

Contacts, rounds, questions and feedback are the person's own notes and are never sent to an AI
(FR-010), so nothing under ``search/workflow``, ``prompts`` or ``platform/llm`` may import this
module (an import-linter contract checks it).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from hiretitan.search.domain.contacts import ContactFields, FieldIssue
from hiretitan.search.domain.interviews import (
    ANSWER_MAX,
    FEEDBACK_MAX,
    INTERVIEWERS_MAX,
    QUESTION_MAX,
    ROUND_KINDS,
    ROUND_STATES,
    RoundSummary,
    can_add_round,
    check_choice,
    check_contact,
    check_round_text,
    check_source,
    status_summary,
)
from hiretitan.search.domain.resume_choice import ResumeChoice, choice_from

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
    resume_file_id: UUID | None
    resume_name: str | None
    resume_added_on: date | None


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
    resume: ResumeChoice


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
    resume = (
        choice_from(details.resume_file_id, details.resume_name, details.resume_added_on)
        if details is not None
        else choice_from(None, None, None)
    )
    return InterviewView(
        job_id=job_id,
        can_edit=in_pipeline,
        can_add_round=in_pipeline and can_add_round(r.state for r in rounds),
        contact=contact,
        source=source,
        rounds=rounds,
        status=StatusView(state=state, round=number),
        resume=resume,
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

    async def lock_job(self, job_id: UUID) -> None: ...


async def writable_job(jobs: JobsLookup, job_id: UUID) -> StoredJob:
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
    await store.lock_job(job_id)  # so a delete or merge cannot slip in between check and write
    await writable_job(jobs, job_id)
    fields, issues = check_contact(
        name=name, role=role, email=email, phone=phone, linkedin_url=linkedin_url
    )
    if fields is None:
        raise InterviewInputError(issues)
    await store.upsert_contact(job_id, fields)


async def remove_contact(jobs: JobsLookup, store: InterviewsWriter, job_id: UUID) -> None:
    await store.lock_job(job_id)
    await writable_job(jobs, job_id)
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
    await store.lock_job(job_id)
    await writable_job(jobs, job_id)
    checked, issues = check_source(kind, firm_name)
    if checked is None:
        raise InterviewInputError(issues)
    await store.set_source(job_id, checked[0], checked[1])


class ProcessFailedError(ValueError):
    """A round failed, so the process has ended and no round can be added (FR-006)."""


class RoundNotFoundError(LookupError):
    """The round does not exist (or was deleted)."""


class StoredRoundRow(StoredRound, Protocol):
    job_id: UUID


class StoredQuestionRow(StoredQuestion, Protocol):
    round_id: UUID


class RoundsStore(InterviewsStore, Protocol):
    async def lock_job(self, job_id: UUID) -> None: ...

    async def get_question(self, question_id: UUID) -> StoredQuestionRow | None: ...

    async def add_question(self, round_id: UUID, question: str, answer: str | None) -> object: ...

    async def update_question(self, question_id: UUID, changes: dict[str, Any]) -> object: ...

    async def delete_question(self, question_id: UUID) -> None: ...

    async def get_round(self, round_id: UUID) -> StoredRoundRow | None: ...

    async def add_round(
        self,
        job_id: UUID,
        *,
        kind: str,
        scheduled_at: datetime | None = None,
        interviewers: str | None = None,
    ) -> object: ...

    async def update_round(self, round_id: UUID, changes: dict[str, Any]) -> object: ...

    async def delete_round(self, round_id: UUID) -> None: ...


def _round_text_checks(
    changes: Mapping[str, Any],
) -> tuple[dict[str, Any], list[FieldIssue]]:
    """Check the fields of a round that were given; the result holds only those fields."""
    checked: dict[str, Any] = {}
    issues: list[FieldIssue] = []
    if "kind" in changes:
        kind, found = check_choice(
            "kind", changes["kind"], ROUND_KINDS, "Pick a round type from the list."
        )
        issues += found
        checked["kind"] = kind
    if "state" in changes:
        state, found = check_choice(
            "state", changes["state"], ROUND_STATES, "A round is scheduled, cleared or failed."
        )
        issues += found
        checked["state"] = state
    if "scheduled_at" in changes:
        checked["scheduled_at"] = changes["scheduled_at"]
    for field, limit in (("interviewers", INTERVIEWERS_MAX), ("feedback", FEEDBACK_MAX)):
        if field in changes:
            text, found = check_round_text(field, changes[field], limit)
            issues += found
            checked[field] = text
    return checked, issues


async def add_round(
    jobs: JobsLookup,
    store: RoundsStore,
    job_id: UUID,
    *,
    kind: str | None,
    scheduled_at: datetime | None = None,
    interviewers: str | None = None,
) -> None:
    """The next round of the job, numbered by the store and starting ``scheduled`` (FR-004)."""
    await store.lock_job(job_id)  # the checks below and the insert happen under one lock
    await writable_job(jobs, job_id)
    checked, issues = _round_text_checks(
        {"kind": kind, "scheduled_at": scheduled_at, "interviewers": interviewers}
    )
    if issues:
        raise InterviewInputError(issues)
    stored = await store.details(job_id)
    if not can_add_round(item.round.state for item in stored.rounds):
        raise ProcessFailedError(
            "A round failed, so no new round can be added. Change that round first."
        )
    await store.add_round(
        job_id,
        kind=checked["kind"],
        scheduled_at=checked["scheduled_at"],
        interviewers=checked["interviewers"],
    )


async def _round_in_pipeline(
    jobs: JobsLookup, store: RoundsStore, round_id: UUID
) -> StoredRoundRow:
    found = await store.get_round(round_id)
    if found is None:
        raise RoundNotFoundError(str(round_id))
    await store.lock_job(found.job_id)
    # read again under the lock: the round may have been removed while this request waited
    found = await store.get_round(round_id)
    if found is None:
        raise RoundNotFoundError(str(round_id))
    await writable_job(jobs, found.job_id)
    return found


async def update_round(
    jobs: JobsLookup, store: RoundsStore, round_id: UUID, changes: Mapping[str, Any]
) -> UUID:
    """Change given round fields (any state change is allowed, US2 AS5). Returns the job id."""
    found = await _round_in_pipeline(jobs, store, round_id)
    checked, issues = _round_text_checks(changes)
    if issues:
        raise InterviewInputError(issues)
    if checked:
        await store.update_round(round_id, checked)
    return found.job_id


async def remove_round(jobs: JobsLookup, store: RoundsStore, round_id: UUID) -> UUID:
    """Delete the round and its questions; the other rounds keep their numbers (research R3)."""
    found = await _round_in_pipeline(jobs, store, round_id)
    await store.delete_round(round_id)
    return found.job_id


class QuestionNotFoundError(LookupError):
    """The question does not exist (or was removed)."""


def _question_checks(
    changes: Mapping[str, Any],
) -> tuple[dict[str, Any], list[FieldIssue]]:
    """Check the question and answer that were given. A question needs text; an answer may be
    empty (it becomes ``None``)."""
    checked: dict[str, Any] = {}
    issues: list[FieldIssue] = []
    if "question" in changes:
        text, found = check_round_text("question", changes["question"], QUESTION_MAX)
        if text is None and not found:
            found = [FieldIssue("question", "Write the question that was asked.")]
        issues += found
        checked["question"] = text
    if "answer" in changes:
        text, found = check_round_text("answer", changes["answer"], ANSWER_MAX)
        issues += found
        checked["answer"] = text
    return checked, issues


async def add_question(
    jobs: JobsLookup,
    store: RoundsStore,
    round_id: UUID,
    *,
    question: str | None,
    answer: str | None = None,
) -> UUID:
    """Add a question (and its answer, if any) after the others in the round; returns the job."""
    found = await _round_in_pipeline(jobs, store, round_id)
    checked, issues = _question_checks({"question": question, "answer": answer})
    if issues:
        raise InterviewInputError(issues)
    await store.add_question(round_id, checked["question"], checked["answer"])
    return found.job_id


async def _question_in_pipeline(jobs: JobsLookup, store: RoundsStore, question_id: UUID) -> UUID:
    found = await store.get_question(question_id)
    if found is None:
        raise QuestionNotFoundError(str(question_id))
    try:
        job_id = (await _round_in_pipeline(jobs, store, found.round_id)).job_id
    except RoundNotFoundError as error:
        raise QuestionNotFoundError(str(question_id)) from error
    if await store.get_question(question_id) is None:  # removed while this request waited
        raise QuestionNotFoundError(str(question_id))
    return job_id


async def update_question(
    jobs: JobsLookup, store: RoundsStore, question_id: UUID, changes: Mapping[str, Any]
) -> UUID:
    """Change the given fields of a question; returns the job id."""
    job_id = await _question_in_pipeline(jobs, store, question_id)
    checked, issues = _question_checks(changes)
    if issues:
        raise InterviewInputError(issues)
    if checked:
        await store.update_question(question_id, checked)
    return job_id


async def remove_question(jobs: JobsLookup, store: RoundsStore, question_id: UUID) -> UUID:
    """Remove one question; the others keep their order."""
    job_id = await _question_in_pipeline(jobs, store, question_id)
    await store.delete_question(question_id)
    return job_id
