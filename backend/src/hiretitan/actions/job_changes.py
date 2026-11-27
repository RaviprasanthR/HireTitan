"""Mikasa's small changes to jobs (002m contracts/actions.md, FR-010 "small change").

Each one calls the same use case as its endpoint (FR-006), returns what changed for the change
record, and has an Undo that puts back the exact earlier state (FR-014). An Undo is refused
(by the change rules) when the job changed since: ``current`` gives the fields it compares.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update

from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, Applied, ChangeView
from hiretitan.actions.text import bounded
from hiretitan.drafts.infra.models import OutreachDraftRow, TailoredResumeRow
from hiretitan.search.application.job_rules import restore_skipped
from hiretitan.search.application.paste import PasteError, PasteInput, paste_job
from hiretitan.search.application.pipeline import (
    PipelineDateError,
    PipelineRuleError,
    mark_applied,
    mark_inquired,
    undo_applied,
    undo_inquired,
)
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.domain.normalize import canonical_url
from hiretitan.search.infra.models import (
    InterviewRoundRow,
    JobRow,
    PipelineDetailsRow,
    RelevanceDecisionRow,
)
from hiretitan.search.infra.paste_store import SqlPasteStore
from hiretitan.search.infra.repos import JobsRepo

NOT_FOUND = ActionError("not_found", "That job is not in HireTitan.")
INVALIDATE = ("jobs", "pipeline", "search-latest")


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) and value else None


async def _extras(ctx: ActionContext, job_id: UUID) -> int:
    """What the person added to the job since: drafts, a tailored resume, interview details."""
    counts = [
        select(func.count()).select_from(OutreachDraftRow).where(OutreachDraftRow.job_id == job_id),
        select(func.count())
        .select_from(TailoredResumeRow)
        .where(TailoredResumeRow.job_id == job_id),
        select(func.count())
        .select_from(InterviewRoundRow)
        .where(InterviewRoundRow.job_id == job_id),
        select(func.count())
        .select_from(PipelineDetailsRow)
        .where(PipelineDetailsRow.job_id == job_id),
    ]
    return sum([await ctx.session.scalar(query) or 0 for query in counts])


async def _status(ctx: ActionContext, job_id: UUID) -> dict[str, Any] | None:
    row = await ctx.session.get(JobRow, job_id, populate_existing=True)
    if row is None:
        return None
    return {
        "state": row.state,
        "applied_on": _iso(row.applied_on),
        "inquired_on": _iso(row.inquired_on),
    }


async def _load(ctx: ActionContext, ref: str) -> JobRow | None:
    row = await ctx.session.get(JobRow, Ref.parse(ref, expect="job").id, populate_existing=True)
    return None if row is None or row.state == "deleted" else row


def _name(row: JobRow) -> str:
    return f"{bounded(row.title).text} at {bounded(row.company_name).text}"


async def current_status(ctx: ActionContext, job_id: UUID) -> Mapping[str, Any] | None:
    return await _status(ctx, job_id)


async def put_status_back(ctx: ActionContext, change: ChangeView) -> None:
    await JobsRepo(ctx.session).set_status(
        change.target_id,
        JobState(change.before["state"]),
        _date(change.before.get("applied_on")),
        _date(change.before.get("inquired_on")),
    )


# ---- mark and unmark -----------------------------------------------------------------------


class MarkArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")
    on: date | None = Field(None, description="The day, if not today (not in the future)")


class JobArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")


async def _mark(
    ctx: ActionContext, args: MarkArgs, which: Literal["applied", "inquired"]
) -> Applied | ActionError:
    row = await _load(ctx, args.job)
    if row is None:
        return NOT_FOUND
    before = await _status(ctx, row.id)
    try:
        if which == "applied":
            await mark_applied(
                JobsRepo(ctx.session), row.id, today=ctx.now.date(), applied_on=args.on
            )
        else:
            await mark_inquired(
                JobsRepo(ctx.session), row.id, today=ctx.now.date(), inquired_on=args.on
            )
    except (PipelineRuleError, PipelineDateError) as error:
        return ActionError(getattr(error, "reason", "bad_date"), str(error))
    after = await _status(ctx, row.id)
    assert before is not None
    assert after is not None
    day = after["applied_on"] if which == "applied" else after["inquired_on"]
    return Applied(
        "job",
        row.id,
        before,
        after,
        f"Marked {_name(row)} as {which} on {day}.",
        [str(Ref("job", row.id))],
    )


async def mark_applied_action(ctx: ActionContext, args: MarkArgs) -> Applied | ActionError:
    return await _mark(ctx, args, "applied")


async def mark_inquired_action(ctx: ActionContext, args: MarkArgs) -> Applied | ActionError:
    return await _mark(ctx, args, "inquired")


async def _unmark(
    ctx: ActionContext, args: JobArgs, which: Literal["applied", "inquired"]
) -> Applied | ActionError:
    row = await _load(ctx, args.job)
    if row is None:
        return NOT_FOUND
    if await _extras(ctx, row.id):
        # The page's own Undo clears the resume used; Mikasa's must be able to put everything
        # back, so a job with details is unmarked on its page.
        return ActionError(
            "has_details",
            "This job has interview details or a resume recorded, so unmark it on its page.",
        )
    before = await _status(ctx, row.id)
    try:
        if which == "applied":
            await undo_applied(JobsRepo(ctx.session), row.id)
        else:
            await undo_inquired(JobsRepo(ctx.session), row.id)
    except PipelineRuleError as error:
        return ActionError(error.reason, str(error))
    after = await _status(ctx, row.id)
    assert before is not None
    assert after is not None
    return Applied(
        "job",
        row.id,
        before,
        after,
        f"{_name(row)} is no longer marked {which}.",
        [str(Ref("job", row.id))],
    )


async def unmark_applied_action(ctx: ActionContext, args: JobArgs) -> Applied | ActionError:
    return await _unmark(ctx, args, "applied")


async def unmark_inquired_action(ctx: ActionContext, args: JobArgs) -> Applied | ActionError:
    return await _unmark(ctx, args, "inquired")


# ---- restore a hidden job ------------------------------------------------------------------


async def _restore_fields(ctx: ActionContext, job_id: UUID) -> Mapping[str, Any] | None:
    row = await ctx.session.get(JobRow, job_id, populate_existing=True)
    return None if row is None else {"state": row.state, "restored": row.restored}


async def restore_job(ctx: ActionContext, args: JobArgs) -> Applied | ActionError:
    row = await _load(ctx, args.job)
    if row is None:
        return NOT_FOUND
    before = {"state": row.state, "restored": row.restored}
    try:
        await restore_skipped(JobsRepo(ctx.session), row.id)
    except PipelineRuleError as error:
        return ActionError(error.reason, str(error))
    return Applied(
        "job",
        row.id,
        before,
        {"state": "explore", "restored": True},
        f"{_name(row)} is back in Explore.",
        [str(Ref("job", row.id))],
    )


async def hide_again(ctx: ActionContext, change: ChangeView) -> None:
    """Undo of a restore: hidden again, with the rule's reason still the current decision."""
    await ctx.session.execute(
        update(JobRow)
        .where(JobRow.id == change.target_id)
        .values(state=change.before["state"], restored=change.before["restored"])
    )


# ---- add a job from a link -----------------------------------------------------------------


class AddJobArgs(BaseModel):
    url: str = Field(max_length=1000, description="The job's link, as the person gave it")
    title: str = Field(min_length=1, max_length=200, description="The job title the person gave")
    company: str = Field(min_length=1, max_length=120, description="The company the person gave")
    location: str | None = Field(None, max_length=120)


class AddAndMarkArgs(AddJobArgs):
    mark: Literal["applied", "inquired"] = "applied"
    on: date | None = Field(None, description="The day, if not today (not in the future)")


async def _added_fields(ctx: ActionContext, job_id: UUID) -> Mapping[str, Any] | None:
    status = await _status(ctx, job_id)
    if status is None:
        return None
    return {**status, "extras": await _extras(ctx, job_id)}


async def _already_there(ctx: ActionContext, url: str) -> ActionError | None:
    canonical = canonical_url(url)
    if canonical is None:
        return None  # the paste rules explain it
    known = await ctx.session.scalar(select(JobRow).where(JobRow.canonical_url == canonical))
    if known is None:
        return None
    if known.state == "deleted":
        return ActionError("deleted_before", "You deleted this job earlier, so it can't be added.")
    return ActionError(
        "already_in_hiretitan",
        f"That job is already in HireTitan as job:{known.id}. Use it instead of adding it again.",
    )


async def _paste(ctx: ActionContext, args: AddJobArgs) -> UUID | ActionError:
    if (found := await _already_there(ctx, args.url)) is not None:
        return found
    try:
        result = await paste_job(
            SqlPasteStore(ctx.session),
            PasteInput(
                url=args.url,
                description="",
                title=args.title,
                company=args.company,
                location=args.location,
                link_only=True,
            ),
            now=ctx.now,
        )
    except PasteError as error:
        return ActionError("invalid", str(error))
    return result.job_id


async def add_job(ctx: ActionContext, args: AddJobArgs) -> Applied | ActionError:
    """Never opens the link (constitution VII, FR-008): only what the person gave is saved."""
    added = await _paste(ctx, args)
    if isinstance(added, ActionError):
        return added
    after = await _added_fields(ctx, added)
    assert after is not None
    ref = str(Ref("job", added))
    return Applied(
        "job", added, {}, dict(after), f"Added {args.title} at {args.company}.", [ref], [ref]
    )


async def add_job_and_mark(ctx: ActionContext, args: AddAndMarkArgs) -> Applied | ActionError:
    added = await _paste(ctx, args)
    if isinstance(added, ActionError):
        return added
    try:
        if args.mark == "applied":
            await mark_applied(
                JobsRepo(ctx.session), added, today=ctx.now.date(), applied_on=args.on
            )
        else:
            await mark_inquired(
                JobsRepo(ctx.session), added, today=ctx.now.date(), inquired_on=args.on
            )
    except (PipelineRuleError, PipelineDateError) as error:
        await ctx.session.rollback()
        return ActionError(getattr(error, "reason", "bad_date"), str(error))
    after = await _added_fields(ctx, added)
    assert after is not None
    ref = str(Ref("job", added))
    day = after["applied_on"] if args.mark == "applied" else after["inquired_on"]
    return Applied(
        "job",
        added,
        {},
        dict(after),
        f"Added {args.title} at {args.company} and marked it {args.mark} on {day}.",
        [ref],
        [ref],
    )


async def remove_added_job(ctx: ActionContext, change: ChangeView) -> None:
    """Undo of an add: the job goes for good, so its link can be added again (research R6).

    The change rules have already checked nothing was added to it since (``extras``)."""
    await ctx.session.execute(
        delete(RelevanceDecisionRow).where(RelevanceDecisionRow.job_id == change.target_id)
    )
    await ctx.session.execute(delete(JobRow).where(JobRow.id == change.target_id))


CHANGES: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="mark_applied",
        description="Mark one job as applied (today, or the day given).",
        args=MarkArgs,
        kind="small",
        handler=mark_applied_action,
        undo=put_status_back,
        current=current_status,
        invalidate=INVALIDATE,
        mirrors=("POST /jobs/{job_id}/applied",),
    ),
    ActionSpec(
        name="unmark_applied",
        description="Take back an applied mark on one job.",
        args=JobArgs,
        kind="small",
        handler=unmark_applied_action,
        undo=put_status_back,
        current=current_status,
        invalidate=INVALIDATE,
        mirrors=("DELETE /jobs/{job_id}/applied",),
    ),
    ActionSpec(
        name="mark_inquired",
        description="Mark one job as inquired (the person asked about it; today or the day given).",
        args=MarkArgs,
        kind="small",
        handler=mark_inquired_action,
        undo=put_status_back,
        current=current_status,
        invalidate=INVALIDATE,
        mirrors=("POST /jobs/{job_id}/inquired",),
    ),
    ActionSpec(
        name="unmark_inquired",
        description="Take back an inquired mark on one job.",
        args=JobArgs,
        kind="small",
        handler=unmark_inquired_action,
        undo=put_status_back,
        current=current_status,
        invalidate=INVALIDATE,
        mirrors=("DELETE /jobs/{job_id}/inquired",),
    ),
    ActionSpec(
        name="restore_job",
        description="Bring one job hidden by the person's rules back to Explore.",
        args=JobArgs,
        kind="small",
        handler=restore_job,
        undo=hide_again,
        current=_restore_fields,
        invalidate=INVALIDATE,
        mirrors=("POST /jobs/{job_id}/restore",),
    ),
    ActionSpec(
        name="add_job",
        description="Add a job from its link with the title and company the person gave. Never "
        "opens the link. Check find_job_by_link first.",
        args=AddJobArgs,
        kind="small",
        handler=add_job,
        undo=remove_added_job,
        current=_added_fields,
        invalidate=INVALIDATE,
        mirrors=("POST /jobs/paste",),
    ),
    ActionSpec(
        name="add_job_and_mark",
        description="Add a job from its link (title and company from the person) and mark it "
        "applied or inquired, as one step with one Undo. Never opens the link.",
        args=AddAndMarkArgs,
        kind="small",
        handler=add_job_and_mark,
        undo=remove_added_job,
        current=_added_fields,
        invalidate=INVALIDATE,
    ),
)
