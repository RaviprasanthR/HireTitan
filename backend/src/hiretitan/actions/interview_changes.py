"""Mikasa's small changes to interview details and the resume used (002m contracts/actions.md).

All private (002e FR-010, 002f FR-013, research R5): the values come from the person's message
and go through the same use cases as the job page; the model gets back a summary that names the
job, and a ref. The change record keeps the values locally for Undo.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select

from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, Applied, ChangeView
from hiretitan.actions.text import bounded
from hiretitan.search.application.interviews import (
    InterviewInputError,
    JobNotFoundError,
    NotInPipelineError,
    ProcessFailedError,
    QuestionNotFoundError,
    RoundNotFoundError,
    add_question,
    add_round,
    save_contact,
    save_source,
    update_question,
    update_round,
)
from hiretitan.search.application.resume_choice import choose_for_job
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.interviews_repo import ROUND_FIELDS, InterviewsRepo
from hiretitan.search.infra.models import (
    InterviewQuestionRow,
    InterviewRoundRow,
    JobRow,
    PipelineDetailsRow,
)
from hiretitan.search.infra.repos import JobsRepo
from hiretitan.search_wiring import SqlResumeLookup

INVALIDATE = ("jobs", "pipeline", "interview")
CONTACT = ("contact_name", "contact_role", "contact_email", "contact_phone", "contact_linkedin")
SOURCE = ("source", "firm_name")
RESUME = ("resume_file_id", "resume_name", "resume_added_on")

_ERRORS: dict[type[Exception], str] = {
    JobNotFoundError: "not_found",
    RoundNotFoundError: "not_found",
    QuestionNotFoundError: "not_found",
    NotInPipelineError: "not_in_pipeline",
    InterviewInputError: "invalid",
    ProcessFailedError: "process_failed",
}


def _refusal(error: Exception) -> ActionError:
    return ActionError(_ERRORS.get(type(error), "invalid"), str(error))


async def _job(ctx: ActionContext, job_id: UUID) -> JobRow | None:
    row = await ctx.session.get(JobRow, job_id, populate_existing=True)
    return None if row is None or row.state == "deleted" else row


def _name(job: JobRow) -> str:
    return f"{bounded(job.title).text} at {bounded(job.company_name).text}"


def _plain(value: Any) -> Any:
    return (
        value.isoformat()
        if hasattr(value, "isoformat")
        else (str(value) if isinstance(value, UUID) else value)
    )


async def _details(ctx: ActionContext, job_id: UUID, names: tuple[str, ...]) -> dict[str, Any]:
    row = await ctx.session.get(PipelineDetailsRow, job_id, populate_existing=True)
    return {name: _plain(getattr(row, name)) if row else None for name in names}


# ---- contact and source --------------------------------------------------------------------


class ContactArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")
    name: str = Field(min_length=1, max_length=120, description="As the person typed it")
    role: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=30)
    linkedin_url: str | None = Field(None, max_length=500)


async def _contact_now(ctx: ActionContext, job_id: UUID) -> Mapping[str, Any] | None:
    return await _details(ctx, job_id, CONTACT)


async def set_interview_contact(ctx: ActionContext, args: ContactArgs) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    job = await _job(ctx, job_id)
    if job is None:
        return ActionError("not_found", "That job is not in HireTitan.")
    before = await _details(ctx, job_id, CONTACT)
    try:
        await save_contact(
            JobsRepo(ctx.session),
            InterviewsRepo(ctx.session),
            job_id,
            **args.model_dump(exclude={"job"}),
        )
    except tuple(_ERRORS) as error:
        return _refusal(error)
    after = await _details(ctx, job_id, CONTACT)
    return Applied(
        "interview",
        job_id,
        before,
        after,
        f"Saved the point of contact for {_name(job)}.",
        [str(Ref("interview", job_id))],
    )


async def put_contact_back(ctx: ActionContext, change: ChangeView) -> None:
    repo = InterviewsRepo(ctx.session)
    before = change.before
    if before["contact_name"] is None:
        await repo.clear_contact(change.target_id)
        return
    await repo.upsert_contact(
        change.target_id,
        ContactFields(
            name=before["contact_name"],
            role=before["contact_role"],
            email=before["contact_email"],
            phone=before["contact_phone"],
            linkedin_url=before["contact_linkedin"],
        ),
    )


class SourceArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")
    kind: Literal["direct", "hiring_firm"] | None = Field(
        description="direct from the company, through a hiring firm, or null to clear it"
    )
    firm_name: str | None = Field(None, max_length=120)


async def _source_now(ctx: ActionContext, job_id: UUID) -> Mapping[str, Any] | None:
    return await _details(ctx, job_id, SOURCE)


async def set_interview_source(ctx: ActionContext, args: SourceArgs) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    job = await _job(ctx, job_id)
    if job is None:
        return ActionError("not_found", "That job is not in HireTitan.")
    before = await _details(ctx, job_id, SOURCE)
    try:
        await save_source(
            JobsRepo(ctx.session),
            InterviewsRepo(ctx.session),
            job_id,
            kind=args.kind,
            firm_name=args.firm_name,
        )
    except tuple(_ERRORS) as error:
        return _refusal(error)
    after = await _details(ctx, job_id, SOURCE)
    return Applied(
        "interview",
        job_id,
        before,
        after,
        f"Saved how {_name(job)} came to you.",
        [str(Ref("interview", job_id))],
    )


async def put_source_back(ctx: ActionContext, change: ChangeView) -> None:
    await InterviewsRepo(ctx.session).set_source(
        change.target_id, change.before["source"], change.before["firm_name"]
    )


# ---- rounds --------------------------------------------------------------------------------


class AddRoundArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")
    kind: Literal["screening", "technical", "hr", "managerial", "other"]
    scheduled_at: AwareDatetime | None = Field(None, description="Date and time with time zone")
    interviewers: str | None = Field(None, max_length=500)


class EditRoundArgs(BaseModel):
    round: str = Field(description="The round's ref, like round:<id>")
    kind: Literal["screening", "technical", "hr", "managerial", "other"] | None = None
    scheduled_at: AwareDatetime | None = None
    interviewers: str | None = Field(None, max_length=500)
    state: Literal["scheduled", "cleared", "failed"] | None = None
    feedback: str | None = Field(None, max_length=5000)


def _round_fields(row: InterviewRoundRow) -> dict[str, Any]:
    return {name: _plain(getattr(row, name)) for name in ROUND_FIELDS}


async def _round_now(ctx: ActionContext, round_id: UUID) -> Mapping[str, Any] | None:
    row = await ctx.session.get(InterviewRoundRow, round_id, populate_existing=True)
    if row is None:
        return None
    questions = await ctx.session.scalar(
        select(func.count())
        .select_from(InterviewQuestionRow)
        .where(InterviewQuestionRow.round_id == round_id)
    )
    return {**_round_fields(row), "questions": questions or 0}


async def add_round_action(ctx: ActionContext, args: AddRoundArgs) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    job = await _job(ctx, job_id)
    if job is None:
        return ActionError("not_found", "That job is not in HireTitan.")
    try:
        await add_round(
            JobsRepo(ctx.session),
            InterviewsRepo(ctx.session),
            job_id,
            kind=args.kind,
            scheduled_at=args.scheduled_at,
            interviewers=args.interviewers,
        )
    except tuple(_ERRORS) as error:
        return _refusal(error)
    added = await ctx.session.scalar(
        select(InterviewRoundRow)
        .where(InterviewRoundRow.job_id == job_id)
        .order_by(InterviewRoundRow.number.desc())
        .limit(1)
    )
    assert added is not None
    after = await _round_now(ctx, added.id)
    assert after is not None
    ref = str(Ref("round", added.id))
    return Applied(
        "round",
        added.id,
        {},
        dict(after),
        f"Added an interview round for {_name(job)}.",
        [ref],
        [ref],
    )


async def remove_added_round(ctx: ActionContext, change: ChangeView) -> None:
    await InterviewsRepo(ctx.session).delete_round(change.target_id)


async def edit_round_action(ctx: ActionContext, args: EditRoundArgs) -> Applied | ActionError:
    round_id = Ref.parse(args.round, expect="round").id
    row = await ctx.session.get(InterviewRoundRow, round_id)
    job = await _job(ctx, row.job_id) if row else None
    if row is None or job is None:
        return ActionError("not_found", "That interview round is not in HireTitan.")
    before = _round_fields(row)
    changes = {name: getattr(args, name) for name in args.model_fields_set - {"round"}}
    if not changes:
        return ActionError("nothing_to_change", "Say what to change about the round.")
    try:
        await update_round(JobsRepo(ctx.session), InterviewsRepo(ctx.session), round_id, changes)
    except tuple(_ERRORS) as error:
        return _refusal(error)
    after = await _round_now(ctx, round_id)
    assert after is not None
    return Applied(
        "round",
        round_id,
        before,
        {name: after[name] for name in ROUND_FIELDS},
        f"Updated an interview round for {_name(job)}.",
        [str(Ref("round", round_id))],
    )


async def _round_fields_now(ctx: ActionContext, round_id: UUID) -> Mapping[str, Any] | None:
    found = await _round_now(ctx, round_id)
    return None if found is None else {name: found[name] for name in ROUND_FIELDS}


async def put_round_back(ctx: ActionContext, change: ChangeView) -> None:
    values = dict(change.before)
    if isinstance(values.get("scheduled_at"), str):
        values["scheduled_at"] = datetime.fromisoformat(values["scheduled_at"])
    await InterviewsRepo(ctx.session).update_round(change.target_id, values)


# ---- questions -----------------------------------------------------------------------------


class AddQuestionArgs(BaseModel):
    round: str = Field(description="The round's ref, like round:<id>")
    question: str = Field(min_length=1, max_length=2000)
    answer: str | None = Field(None, max_length=10_000)


class EditQuestionArgs(BaseModel):
    question_ref: str = Field(description="The question's ref, like question:<id>")
    question: str | None = Field(None, max_length=2000)
    answer: str | None = Field(None, max_length=10_000)


async def _question_now(ctx: ActionContext, question_id: UUID) -> Mapping[str, Any] | None:
    row = await ctx.session.get(InterviewQuestionRow, question_id, populate_existing=True)
    return None if row is None else {"question": row.question, "answer": row.answer}


async def add_question_action(ctx: ActionContext, args: AddQuestionArgs) -> Applied | ActionError:
    round_id = Ref.parse(args.round, expect="round").id
    try:
        job_id = await add_question(
            JobsRepo(ctx.session),
            InterviewsRepo(ctx.session),
            round_id,
            question=args.question,
            answer=args.answer,
        )
    except tuple(_ERRORS) as error:
        return _refusal(error)
    job = await _job(ctx, job_id)
    added = await ctx.session.scalar(
        select(InterviewQuestionRow)
        .where(InterviewQuestionRow.round_id == round_id)
        .order_by(InterviewQuestionRow.position.desc())
        .limit(1)
    )
    assert added is not None
    assert job is not None
    ref = str(Ref("question", added.id))
    return Applied(
        "question",
        added.id,
        {},
        {"question": added.question, "answer": added.answer},
        f"Added an interview question for {_name(job)}.",
        [ref],
        [ref],
    )


async def remove_added_question(ctx: ActionContext, change: ChangeView) -> None:
    await InterviewsRepo(ctx.session).delete_question(change.target_id)


async def edit_question_action(ctx: ActionContext, args: EditQuestionArgs) -> Applied | ActionError:
    question_id = Ref.parse(args.question_ref, expect="question").id
    before = await _question_now(ctx, question_id)
    if before is None:
        return ActionError("not_found", "That question is not in HireTitan.")
    changes = {name: getattr(args, name) for name in args.model_fields_set - {"question_ref"}}
    if not changes:
        return ActionError("nothing_to_change", "Say what to change about the question.")
    try:
        job_id = await update_question(
            JobsRepo(ctx.session), InterviewsRepo(ctx.session), question_id, changes
        )
    except tuple(_ERRORS) as error:
        return _refusal(error)
    job = await _job(ctx, job_id)
    after = await _question_now(ctx, question_id)
    assert job is not None
    assert after is not None
    return Applied(
        "question",
        question_id,
        dict(before),
        dict(after),
        f"Updated an interview question for {_name(job)}.",
        [str(Ref("question", question_id))],
    )


async def put_question_back(ctx: ActionContext, change: ChangeView) -> None:
    await InterviewsRepo(ctx.session).update_question(change.target_id, dict(change.before))


# ---- the resume used -----------------------------------------------------------------------


class ResumeArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")
    resume_file: str = Field(description="The file's ref, like resume_file:<id>")


async def _resume_now(ctx: ActionContext, job_id: UUID) -> Mapping[str, Any] | None:
    return await _details(ctx, job_id, RESUME)


async def set_resume_used(ctx: ActionContext, args: ResumeArgs) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    file_id = Ref.parse(args.resume_file, expect="resume_file").id
    job = await _job(ctx, job_id)
    if job is None:
        return ActionError("not_found", "That job is not in HireTitan.")
    before = await _details(ctx, job_id, RESUME)
    try:
        await choose_for_job(
            JobsRepo(ctx.session),
            SqlResumeLookup(ctx.session),
            InterviewsRepo(ctx.session),
            job_id,
            file_id,
        )
    except tuple(_ERRORS) as error:
        return _refusal(error)
    after = await _details(ctx, job_id, RESUME)
    return Applied(
        "interview",
        job_id,
        before,
        after,
        f"Recorded the resume you used for {_name(job)}.",
        [str(Ref("interview", job_id))],
    )


async def put_resume_back(ctx: ActionContext, change: ChangeView) -> None:
    repo = InterviewsRepo(ctx.session)
    before = change.before
    if before["resume_file_id"] is None and before["resume_name"] is None:
        await repo.clear_resume(change.target_id)
        return
    await repo.set_resume(
        change.target_id,
        UUID(before["resume_file_id"]),
        before["resume_name"],
        datetime.fromisoformat(before["resume_added_on"]).date(),
    )


def _spec(
    name: str,
    description: str,
    args: type[BaseModel],
    handler: Any,
    undo: Any,
    current: Any,
    mirrors: tuple[str, ...],
) -> ActionSpec:
    return ActionSpec(
        name=name,
        description=description,
        args=args,
        kind="small",
        private=True,
        handler=handler,
        undo=undo,
        current=current,
        invalidate=INVALIDATE,
        mirrors=mirrors,
    )


CHANGES: tuple[ActionSpec, ...] = (
    _spec(
        "set_interview_contact",
        "Save the point of contact for a pipeline job, as the person typed it.",
        ContactArgs,
        set_interview_contact,
        put_contact_back,
        _contact_now,
        ("PUT /jobs/{job_id}/interview/contact",),
    ),
    _spec(
        "set_interview_source",
        "Save how a pipeline job came: direct, or through a hiring firm (with its name).",
        SourceArgs,
        set_interview_source,
        put_source_back,
        _source_now,
        ("PUT /jobs/{job_id}/interview/source",),
    ),
    _spec(
        "add_round",
        "Add the next interview round to a pipeline job.",
        AddRoundArgs,
        add_round_action,
        remove_added_round,
        _round_now,
        ("POST /jobs/{job_id}/interview/rounds",),
    ),
    _spec(
        "edit_round",
        "Change an interview round: type, date and time, interviewers, state or feedback.",
        EditRoundArgs,
        edit_round_action,
        put_round_back,
        _round_fields_now,
        ("PATCH /interview/rounds/{round_id}",),
    ),
    _spec(
        "add_question",
        "Add a question (and its answer) to an interview round.",
        AddQuestionArgs,
        add_question_action,
        remove_added_question,
        _question_now,
        ("POST /interview/rounds/{round_id}/questions",),
    ),
    _spec(
        "edit_question",
        "Change an interview question or its answer.",
        EditQuestionArgs,
        edit_question_action,
        put_question_back,
        _question_now,
        ("PATCH /interview/questions/{question_id}",),
    ),
    _spec(
        "set_resume_used",
        "Record which stored resume file the person used for a pipeline job.",
        ResumeArgs,
        set_resume_used,
        put_resume_back,
        _resume_now,
        ("PUT /jobs/{job_id}/interview/resume",),
    ),
)
