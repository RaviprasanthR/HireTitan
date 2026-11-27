"""Mikasa's drafts and tailored resume (002m US3, FR-008a, FR-009).

Writing goes through the same use cases as the job page's Write and Tailor buttons, so a contact
recipient stays behind placeholders and never reaches the AI. Nothing here edits draft or resume
text (FR-008a), and reads give refs and states, never the text. Every change waits on a confirm
card.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from hiretitan.actions.refs import Ref, label_contact
from hiretitan.actions.spec import (
    ActionContext,
    ActionError,
    ActionRefusedError,
    ActionSpec,
    Applied,
    ReadResult,
)
from hiretitan.actions.text import bounded
from hiretitan.drafts.infra.models import OutreachDraftRow
from hiretitan.drafts.infra.repos import DraftsRepo, TailoredRepo
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.repos import ContactsRepo

Targets = Mapping[str, Mapping[str, Any]]
INVALIDATE = ("drafts", "tailored-resume", "jobs")
_KIND_NAME = {"connection_request": "LinkedIn connection message", "referral_message": "message"}


class JobOnly(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")


class WriteDraftArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")
    contact: str | None = Field(
        default=None, description="A saved contact at the job's company, like contact:<id>"
    )
    name: str | None = Field(
        default=None, max_length=120, description="The recipient's name when not a saved contact"
    )
    role: str | None = Field(default=None, max_length=120, description="The recipient's role")


class DraftArgs(BaseModel):
    draft: str = Field(description="The draft's ref, like draft:<id>")


def _label(row: JobRow) -> str:
    return f"{bounded(row.title).text} at {bounded(row.company_name).text}"


async def _job_row(ctx: ActionContext, ref: str) -> JobRow | None:
    row = await ctx.session.get(JobRow, Ref.parse(ref, expect="job").id, populate_existing=True)
    return None if row is None or row.state == "deleted" else row


async def _write_targets(ctx: ActionContext, args: WriteDraftArgs) -> Targets:
    row = await _job_row(ctx, args.job)
    if row is None:
        return {}
    found: dict[str, Mapping[str, Any]] = {str(Ref("job", row.id)): {"label": _label(row)}}
    if args.contact:
        contact = await ContactsRepo(ctx.session).get(Ref.parse(args.contact, expect="contact").id)
        if contact is None or contact.company_id != row.company_id:
            return {}
        found[str(Ref("contact", contact.id))] = {"label": label_contact(row.company_name)}
    return found


def _writer(kind: str) -> Any:
    async def write(ctx: ActionContext, args: WriteDraftArgs) -> Applied | ActionError:
        start = ctx.services.start_draft
        if start is None:
            return ActionError("unavailable", "Drafts can't be written from here.")
        row = await _job_row(ctx, args.job)
        if row is None:
            return ActionError("not_found", "That job is not in HireTitan.")
        contact_id = Ref.parse(args.contact, expect="contact").id if args.contact else None
        try:
            draft_id = await start(row.id, kind, contact_id, args.name, args.role)
        except ActionRefusedError as error:
            return ActionError(error.reason, str(error))
        what = _KIND_NAME.get(kind, kind)
        summary = f"Started a {what} draft for {_label(row)}."
        return Applied("draft", draft_id, {}, {}, summary, [str(Ref("draft", draft_id))])

    return write


async def tailor_resume(ctx: ActionContext, args: JobOnly) -> Applied | ActionError:
    start = ctx.services.start_tailor
    if start is None:
        return ActionError("unavailable", "A resume can't be tailored from here.")
    row = await _job_row(ctx, args.job)
    if row is None:
        return ActionError("not_found", "That job is not in HireTitan.")
    try:
        resume_id = await start(row.id)
    except ActionRefusedError as error:
        return ActionError(error.reason, str(error))
    summary = f"Started a tailored resume for {_label(row)}."
    ref = str(Ref("tailored_resume", resume_id))
    return Applied("tailored_resume", resume_id, {}, {}, summary, [ref])


async def _job_target(ctx: ActionContext, args: JobOnly) -> Targets:
    row = await _job_row(ctx, args.job)
    return {str(Ref("job", row.id)): {"label": _label(row)}} if row else {}


async def _draft_target(ctx: ActionContext, args: DraftArgs) -> Targets:
    draft_id = Ref.parse(args.draft, expect="draft").id
    row = await ctx.session.get(OutreachDraftRow, draft_id, populate_existing=True)
    if row is None:
        return {}
    fields = {"label": "a draft", "status": row.status, "edited": row.edited}
    return {str(Ref("draft", row.id)): fields}


async def delete_draft(ctx: ActionContext, args: DraftArgs) -> Applied | ActionError:
    draft_id = Ref.parse(args.draft, expect="draft").id
    row = await ctx.session.get(OutreachDraftRow, draft_id)
    if row is None:
        return ActionError("not_found", "That draft is not in HireTitan.")
    if row.status == "writing":
        return ActionError("draft_in_progress", "This draft is still being written.")
    await DraftsRepo(ctx.session).remove(draft_id)
    return Applied("draft", draft_id, {"status": row.status}, {}, "Deleted the draft.")


async def delete_tailored_resume(ctx: ActionContext, args: JobOnly) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    row = await TailoredRepo(ctx.session).get_for_job(job_id)
    if row is None:
        return ActionError("not_tailored", "There is no tailored resume for this job.")
    if row.status == "writing":
        return ActionError("resume_in_progress", "This resume is still being written.")
    await TailoredRepo(ctx.session).remove_for_job(job_id)
    summary = "Deleted the tailored resume."
    return Applied("tailored_resume", row.id, {"status": row.status}, {}, summary)


async def list_drafts(ctx: ActionContext, args: JobOnly) -> ReadResult:
    rows = await DraftsRepo(ctx.session).list_for_job(Ref.parse(args.job, expect="job").id)
    items = [
        {
            "ref": str(Ref("draft", r.id)),
            "kind": r.kind,
            "status": r.status,
            "recipient_kind": r.recipient_kind,  # never the recipient's name or the text
            "edited": r.edited,
        }
        for r in rows
    ]
    return ReadResult(items, len(items))


async def get_tailored_resume(ctx: ActionContext, args: JobOnly) -> ReadResult:
    row = await TailoredRepo(ctx.session).get_for_job(Ref.parse(args.job, expect="job").id)
    if row is None:
        return ReadResult([], 0)
    item = {"ref": str(Ref("tailored_resume", row.id)), "status": row.status, "edited": row.edited}
    return ReadResult([item], 1)


def _risky(
    name: str,
    description: str,
    args: type[BaseModel],
    handler: Any,
    targets: Any,
    title: str,
    mirrors: tuple[str, ...],
) -> ActionSpec:
    return ActionSpec(
        name=name,
        description=description,
        args=args,
        kind="risky",
        handler=handler,
        targets=targets,
        card_title=title,
        invalidate=INVALIDATE,
        mirrors=mirrors,
    )


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        "list_drafts",
        "List the drafts written for a job: refs, kind and state only, never the text.",
        JobOnly,
        "read",
        list_drafts,
    ),
    ActionSpec(
        "get_tailored_resume",
        "Say whether a job has a tailored resume: its ref and state, never its text.",
        JobOnly,
        "read",
        get_tailored_resume,
    ),
)

CHANGES: tuple[ActionSpec, ...] = (
    _risky(
        "draft_connection_request",
        "Write a LinkedIn connection message for a job. The person sends it themselves.",
        WriteDraftArgs,
        _writer("connection_request"),
        _write_targets,
        "Write a connection message",
        ("POST /jobs/{job_id}/drafts",),
    ),
    _risky(
        "draft_referral_message",
        "Write a message asking for a referral for a job. The person sends it themselves.",
        WriteDraftArgs,
        _writer("referral_message"),
        _write_targets,
        "Write a referral message",
        (),
    ),
    _risky(
        "tailor_resume",
        "Tailor the resume to a job from the confirmed profile. Nothing is invented.",
        JobOnly,
        tailor_resume,
        _job_target,
        "Tailor the resume",
        ("POST /jobs/{job_id}/tailored-resume",),
    ),
    _risky(
        "delete_draft",
        "Delete one draft.",
        DraftArgs,
        delete_draft,
        _draft_target,
        "Delete",
        ("DELETE /drafts/{draft_id}",),
    ),
    _risky(
        "delete_tailored_resume",
        "Delete a job's tailored resume.",
        JobOnly,
        delete_tailored_resume,
        _job_target,
        "Delete",
        ("DELETE /jobs/{job_id}/tailored-resume",),
    ),
)
