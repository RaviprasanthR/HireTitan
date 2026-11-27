"""Mikasa's risky changes to companies, contacts, interview details and the resume used
(002m contracts/actions.md). Each waits on a confirm card; deletes cannot be undone, as on the
pages. Contact, round and question cards name the job or company, never the private details."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, Applied
from hiretitan.actions.text import bounded
from hiretitan.search.application.companies import (
    CompanyNotFoundError,
    delete_company,
    hide_company,
)
from hiretitan.search.application.contacts import ContactNotFoundError, delete_contact
from hiretitan.search.application.discovery import DiscoveryError, confirm_board, reject_board
from hiretitan.search.application.interviews import (
    JobNotFoundError,
    NotInPipelineError,
    QuestionNotFoundError,
    RoundNotFoundError,
    remove_contact,
    remove_question,
    remove_round,
)
from hiretitan.search.application.resume_choice import clear_for_job
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import (
    CompanyRow,
    ContactRow,
    InterviewQuestionRow,
    InterviewRoundRow,
    JobRow,
    PipelineDetailsRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, JobsRepo

Targets = Mapping[str, Mapping[str, Any]]
INVALIDATE = ("companies", "contacts", "jobs", "pipeline", "interview")
_NOT_FOUND = (
    CompanyNotFoundError,
    ContactNotFoundError,
    JobNotFoundError,
    RoundNotFoundError,
    QuestionNotFoundError,
)


async def _company(ctx: ActionContext, ref: str) -> CompanyRow | None:
    row = await ctx.session.get(
        CompanyRow, Ref.parse(ref, expect="company").id, populate_existing=True
    )
    return None if row is None or row.deleted_at is not None else row


def _company_target(row: CompanyRow) -> dict[str, Mapping[str, Any]]:
    return {
        str(Ref("company", row.id)): {
            "label": bounded(row.name).text,
            "hidden": row.hidden,
            "careers": row.careers_url,
            "board": row.board_id,
        }
    }


# ---- companies -----------------------------------------------------------------------------


class CompanyArgs(BaseModel):
    company: str = Field(description="The company's ref, like company:<id>")


class HideCompaniesArgs(BaseModel):
    companies: list[str] = Field(min_length=2, max_length=100, description="Company refs, 2 to 25")
    hidden: bool = Field(True, description="True hides them from searches; false shows them again")


async def _one_company(ctx: ActionContext, args: CompanyArgs) -> Targets:
    row = await _company(ctx, args.company)
    return {} if row is None else _company_target(row)


async def _many_companies(ctx: ActionContext, args: HideCompaniesArgs) -> Targets:
    found: dict[str, Mapping[str, Any]] = {}
    for ref in args.companies:
        if (row := await _company(ctx, ref)) is not None:
            found.update(_company_target(row))
    return found


async def hide_companies(
    ctx: ActionContext, args: HideCompaniesArgs
) -> list[Applied] | ActionError:
    done: list[Applied] = []
    for ref in args.companies:
        row = await _company(ctx, ref)
        if row is None:
            return ActionError("not_found", f"{ref} is not in HireTitan.")
        before = {"hidden": row.hidden}
        await hide_company(CompaniesRepo(ctx.session), row.id, hidden=args.hidden)
        word = "Hid" if args.hidden else "Showed"
        done.append(
            Applied(
                "company",
                row.id,
                before,
                {"hidden": args.hidden},
                f"{word} {bounded(row.name).text}.",
            )
        )
    return done


async def delete_company_action(ctx: ActionContext, args: CompanyArgs) -> Applied | ActionError:
    row = await _company(ctx, args.company)
    if row is None:
        return ActionError("not_found", "That company is not in HireTitan.")
    name = bounded(row.name).text
    try:
        await delete_company(CompaniesRepo(ctx.session), row.id, now=ctx.now)
    except CompanyNotFoundError:
        return ActionError("not_found", "That company is not in HireTitan.")
    return Applied("company", row.id, {"deleted": False}, {"deleted": True}, f"Deleted {name}.")


async def _board(ctx: ActionContext, args: CompanyArgs, use: bool) -> Applied | ActionError:
    careers = ctx.services.careers
    if careers is None:
        return ActionError("unavailable", "Boards can't be checked from here.")
    row = await _company(ctx, args.company)
    if row is None:
        return ActionError("not_found", "That company is not in HireTitan.")
    try:
        view = await (confirm_board if use else reject_board)(
            CompaniesRepo(ctx.session), careers, row.id
        )
    except CompanyNotFoundError:
        return ActionError("not_found", "That company is not in HireTitan.")
    except DiscoveryError as error:
        return ActionError("no_board", str(error))
    word = "will read its job board" if use else "will read its careers page instead of a board"
    return Applied(
        "company", row.id, {}, {"board": view.board_status}, f"{bounded(row.name).text} {word}."
    )


async def confirm_board_action(ctx: ActionContext, args: CompanyArgs) -> Applied | ActionError:
    return await _board(ctx, args, use=True)


async def reject_board_action(ctx: ActionContext, args: CompanyArgs) -> Applied | ActionError:
    return await _board(ctx, args, use=False)


# ---- contacts ------------------------------------------------------------------------------


class ContactArgs(BaseModel):
    contact: str = Field(description="The contact's ref, like contact:<id>")


async def _contact_target(ctx: ActionContext, args: ContactArgs) -> Targets:
    contact = await ctx.session.get(
        ContactRow, Ref.parse(args.contact, expect="contact").id, populate_existing=True
    )
    if contact is None:
        return {}
    company = await ctx.session.get(CompanyRow, contact.company_id)
    name = bounded(company.name).text if company else "a company"
    # the card shows the label; the fingerprint covers the contact's fields, never sent anywhere
    return {
        str(Ref("contact", contact.id)): {
            "label": f"a contact at {name}",
            "name": contact.name,
            "email": contact.email,
        }
    }


async def delete_contact_action(ctx: ActionContext, args: ContactArgs) -> Applied | ActionError:
    contact_id = Ref.parse(args.contact, expect="contact").id
    contact = await ctx.session.get(ContactRow, contact_id)
    if contact is None:
        return ActionError("not_found", "That contact is not in HireTitan.")
    company = await ctx.session.get(CompanyRow, contact.company_id)
    try:
        await delete_contact(
            CompaniesRepo(ctx.session), ContactsRepo(ctx.session), contact.company_id, contact_id
        )
    except _NOT_FOUND:
        return ActionError("not_found", "That contact is not in HireTitan.")
    where = bounded(company.name).text if company else "a company"
    return Applied("contact", contact_id, {}, {"deleted": True}, f"Deleted a contact at {where}.")


# ---- interview details and the resume used -------------------------------------------------


def _job_label(job: JobRow) -> str:
    return f"{bounded(job.title).text} at {bounded(job.company_name).text}"


class RoundArgs(BaseModel):
    round: str = Field(description="The round's ref, like round:<id>")


class QuestionArgs(BaseModel):
    question: str = Field(description="The question's ref, like question:<id>")


class JobArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")


async def _round_target(ctx: ActionContext, args: RoundArgs) -> Targets:
    row = await ctx.session.get(
        InterviewRoundRow, Ref.parse(args.round, expect="round").id, populate_existing=True
    )
    job = await ctx.session.get(JobRow, row.job_id) if row else None
    if row is None or job is None:
        return {}
    return {
        str(Ref("round", row.id)): {
            "label": f"round {row.number} for {_job_label(job)}",
            "state": row.state,
            "at": row.scheduled_at,
        }
    }


async def _question_target(ctx: ActionContext, args: QuestionArgs) -> Targets:
    row = await ctx.session.get(
        InterviewQuestionRow, Ref.parse(args.question, expect="question").id, populate_existing=True
    )
    round_row = await ctx.session.get(InterviewRoundRow, row.round_id) if row else None
    job = await ctx.session.get(JobRow, round_row.job_id) if round_row else None
    if row is None or job is None:
        return {}
    return {
        str(Ref("question", row.id)): {
            "label": f"a question for {_job_label(job)}",
            "q": row.question,
        }
    }


async def _job_details_target(ctx: ActionContext, args: JobArgs) -> Targets:
    job = await ctx.session.get(JobRow, Ref.parse(args.job, expect="job").id)
    details = (
        await ctx.session.get(PipelineDetailsRow, job.id, populate_existing=True) if job else None
    )
    if job is None or details is None:
        return {}
    return {
        str(Ref("interview", job.id)): {
            "label": _job_label(job),
            "contact": details.contact_name,
            "resume": details.resume_name,
        }
    }


async def delete_round(ctx: ActionContext, args: RoundArgs) -> Applied | ActionError:
    round_id = Ref.parse(args.round, expect="round").id
    try:
        job_id = await remove_round(JobsRepo(ctx.session), InterviewsRepo(ctx.session), round_id)
    except (*_NOT_FOUND, NotInPipelineError) as error:
        return ActionError("not_found", str(error) or "That round is not in HireTitan.")
    job = await ctx.session.get(JobRow, job_id)
    label = _job_label(job) if job else "the job"
    return Applied(
        "round", round_id, {}, {"deleted": True}, f"Deleted an interview round for {label}."
    )


async def delete_question(ctx: ActionContext, args: QuestionArgs) -> Applied | ActionError:
    question_id = Ref.parse(args.question, expect="question").id
    try:
        job_id = await remove_question(
            JobsRepo(ctx.session), InterviewsRepo(ctx.session), question_id
        )
    except (*_NOT_FOUND, NotInPipelineError) as error:
        return ActionError("not_found", str(error) or "That question is not in HireTitan.")
    job = await ctx.session.get(JobRow, job_id)
    label = _job_label(job) if job else "the job"
    return Applied(
        "question",
        question_id,
        {},
        {"deleted": True},
        f"Deleted an interview question for {label}.",
    )


async def clear_interview_contact(ctx: ActionContext, args: JobArgs) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    job = await ctx.session.get(JobRow, job_id)
    try:
        await remove_contact(JobsRepo(ctx.session), InterviewsRepo(ctx.session), job_id)
    except (*_NOT_FOUND, NotInPipelineError) as error:
        return ActionError("not_found", str(error) or "That job is not in HireTitan.")
    label = _job_label(job) if job else "the job"
    return Applied(
        "interview", job_id, {}, {"contact": None}, f"Removed the point of contact for {label}."
    )


async def clear_resume_used(ctx: ActionContext, args: JobArgs) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    job = await ctx.session.get(JobRow, job_id)
    try:
        await clear_for_job(JobsRepo(ctx.session), InterviewsRepo(ctx.session), job_id)
    except (*_NOT_FOUND, NotInPipelineError) as error:
        return ActionError("not_found", str(error) or "That job is not in HireTitan.")
    label = _job_label(job) if job else "the job"
    return Applied(
        "interview", job_id, {}, {"resume": None}, f"Cleared the resume used for {label}."
    )


def _risky(
    name: str,
    description: str,
    args: type[BaseModel],
    handler: Any,
    targets: Any,
    title: str,
    mirrors: tuple[str, ...],
    private: bool = False,
) -> ActionSpec:
    return ActionSpec(
        name=name,
        description=description,
        args=args,
        kind="risky",
        private=private,
        handler=handler,
        targets=targets,
        card_title=title,
        invalidate=INVALIDATE,
        mirrors=mirrors,
    )


CHANGES: tuple[ActionSpec, ...] = (
    _risky(
        "hide_companies",
        "Hide 2 to 25 companies from searches, or show them again.",
        HideCompaniesArgs,
        hide_companies,
        _many_companies,
        "Hide or show",
        ("PATCH /companies/{company_id}",),
    ),
    _risky(
        "delete_company",
        "Delete a company from the list.",
        CompanyArgs,
        delete_company_action,
        _one_company,
        "Delete",
        ("DELETE /companies/{company_id}",),
    ),
    _risky(
        "confirm_board",
        "Use the job board found behind a company's careers page.",
        CompanyArgs,
        confirm_board_action,
        _one_company,
        "Use the job board of",
        ("POST /companies/{company_id}/discovery/confirm",),
    ),
    _risky(
        "reject_board",
        "Read a company's careers page instead of the board found behind it.",
        CompanyArgs,
        reject_board_action,
        _one_company,
        "Read the careers page of",
        ("POST /companies/{company_id}/discovery/reject",),
    ),
    _risky(
        "delete_contact",
        "Delete a contact (a contact ref).",
        ContactArgs,
        delete_contact_action,
        _contact_target,
        "Delete",
        ("DELETE /companies/{company_id}/contacts/{contact_id}",),
        private=True,
    ),
    _risky(
        "delete_round",
        "Delete an interview round and its questions.",
        RoundArgs,
        delete_round,
        _round_target,
        "Delete",
        ("DELETE /interview/rounds/{round_id}",),
        private=True,
    ),
    _risky(
        "delete_question",
        "Delete an interview question.",
        QuestionArgs,
        delete_question,
        _question_target,
        "Delete",
        ("DELETE /interview/questions/{question_id}",),
        private=True,
    ),
    _risky(
        "clear_interview_contact",
        "Remove a pipeline job's point of contact.",
        JobArgs,
        clear_interview_contact,
        _job_details_target,
        "Remove the point of contact for",
        ("DELETE /jobs/{job_id}/interview/contact",),
        private=True,
    ),
    _risky(
        "clear_resume_used",
        "Clear which resume was used for a pipeline job.",
        JobArgs,
        clear_resume_used,
        _job_details_target,
        "Clear the resume used for",
        ("DELETE /jobs/{job_id}/interview/resume",),
        private=True,
    ),
)
