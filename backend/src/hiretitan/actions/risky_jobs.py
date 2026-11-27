"""Mikasa's risky changes to jobs, searches and job-alert mail (002m contracts/actions.md).

Each waits on a confirm card (FR-010). ``targets`` names what the card touches, fingerprinted
when proposed and checked again on confirm (R7). The bulk forms change up to 25 jobs and give
each its own change record, so each can be undone (US2 scenario 8).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from hiretitan.actions.job_changes import (
    INVALIDATE,
    MarkArgs,
    current_status,
    hide_again,
    mark_applied_action,
    mark_inquired_action,
    put_status_back,
    restore_job,
)
from hiretitan.actions.job_changes import JobArgs as OneJob
from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import (
    ActionContext,
    ActionError,
    ActionRefusedError,
    ActionSpec,
    Applied,
)
from hiretitan.actions.text import bounded
from hiretitan.mail.application.ports import CheckNotReadyError
from hiretitan.mail.domain.senders import SenderError
from hiretitan.mail.infra.models import MailSenderRow
from hiretitan.mail.infra.repos import BuiltInSenderError, SenderExistsError, SendersRepo
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.application.job_rules import check_recheckable
from hiretitan.search.application.pipeline import PipelineRuleError
from hiretitan.search.application.rules import RulesNotApprovedError
from hiretitan.search.application.search import (
    SearchAlreadyRunningError,
    SearchNotRunningError,
    SetupIncompleteError,
    request_stop,
)
from hiretitan.search.domain.job_state import IllegalJobTransitionError, JobState
from hiretitan.search.infra.job_ops import (
    JobGoneError,
    PairDecidedError,
    PairNotFoundError,
    delete_job,
    dismiss_pair,
    merge_pair,
)
from hiretitan.search.infra.models import JobRow, PossibleDuplicateRow, SearchRunRow
from hiretitan.search.infra.repos import DecisionsRepo
from hiretitan.search.infra.search_store import SearchStore
from hiretitan.search.workflow.recheck import RECHECK_WORKFLOW

Targets = Mapping[str, Mapping[str, Any]]


def _label(row: JobRow) -> str:
    return f"{bounded(row.title).text} at {bounded(row.company_name).text}"


async def _job_target(ctx: ActionContext, ref: str) -> Targets:
    row = await ctx.session.get(JobRow, Ref.parse(ref, expect="job").id, populate_existing=True)
    if row is None or row.state == "deleted":
        return {}
    return {
        str(Ref("job", row.id)): {
            "label": _label(row),
            "state": row.state,
            "applied_on": row.applied_on,
            "inquired_on": row.inquired_on,
        }
    }


async def _one_job(ctx: ActionContext, args: OneJob) -> Targets:
    return await _job_target(ctx, args.job)


# ---- delete and recheck --------------------------------------------------------------------


async def delete_job_action(ctx: ActionContext, args: OneJob) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    row = await ctx.session.get(JobRow, job_id)
    if row is None:
        return ActionError("not_found", "That job is not in HireTitan.")
    before = {"state": row.state}
    label = _label(row)
    try:
        await delete_job(ctx.session, job_id, ctx.services.job_cleanups)
    except JobGoneError:
        return ActionError("not_found", "That job is not in HireTitan.")
    except IllegalJobTransitionError as error:
        return ActionError("not_allowed", str(error))
    return Applied("job", job_id, before, {"state": "deleted"}, f"Deleted {label}.")


async def recheck_job(ctx: ActionContext, args: OneJob) -> Applied | ActionError:
    job_id = Ref.parse(args.job, expect="job").id
    row = await ctx.session.get(JobRow, job_id)
    if row is None or row.state == "deleted":
        return ActionError("not_found", "That job is not in HireTitan.")
    current = await DecisionsRepo(ctx.session).current(job_id)
    try:
        check_recheckable(JobState(row.state), current.decided_by if current else None)
    except PipelineRuleError as error:
        return ActionError(error.reason, str(error))
    run = await RunsRepo(ctx.session).create(RECHECK_WORKFLOW, subject_id=job_id)
    queue = ctx.services.queue

    async def enqueue() -> None:
        if queue is not None:
            await queue.enqueue(run.id)

    return Applied(
        "job",
        job_id,
        {},
        {"recheck_run": str(run.id)},
        f"Asked the AI to check {_label(row)}.",
        [str(Ref("job", job_id))],
        after_commit=enqueue,
    )


# ---- duplicates ----------------------------------------------------------------------------


class PairArgs(BaseModel):
    duplicate: str = Field(description="The pair's ref, like duplicate:<id>")


async def _pair_target(ctx: ActionContext, args: PairArgs) -> Targets:
    pair = await ctx.session.get(
        PossibleDuplicateRow,
        Ref.parse(args.duplicate, expect="duplicate").id,
        populate_existing=True,
    )
    if pair is None:
        return {}
    a = await ctx.session.get(JobRow, pair.job_a_id)
    b = await ctx.session.get(JobRow, pair.job_b_id)
    label = " and ".join(_label(j) for j in (a, b) if j is not None)
    return {str(Ref("duplicate", pair.id)): {"label": label, "status": pair.status}}


async def _decide(ctx: ActionContext, args: PairArgs, merge: bool) -> Applied | ActionError:
    pair_id = Ref.parse(args.duplicate, expect="duplicate").id
    try:
        pair = await (merge_pair if merge else dismiss_pair)(ctx.session, pair_id, ctx.now)
    except PairNotFoundError:
        return ActionError("not_found", "That pair is not in HireTitan.")
    except PairDecidedError as error:
        return ActionError("already_decided", str(error))
    word = "Merged" if merge else "Kept apart"
    return Applied(
        "duplicate",
        pair.id,
        {"status": "open"},
        {"status": pair.status},
        f"{word} the two jobs.",
        [str(Ref("job", pair.job_a_id))],
    )


async def merge_duplicate(ctx: ActionContext, args: PairArgs) -> Applied | ActionError:
    return await _decide(ctx, args, merge=True)


async def dismiss_duplicate(ctx: ActionContext, args: PairArgs) -> Applied | ActionError:
    return await _decide(ctx, args, merge=False)


# ---- bulk marks and restores ---------------------------------------------------------------


class ManyJobsArgs(BaseModel):
    jobs: list[str] = Field(min_length=1, max_length=100, description="Job refs, 1 to 25")
    on: date | None = Field(None, description="The day, if not today (not in the future)")


async def _many_targets(ctx: ActionContext, args: ManyJobsArgs) -> Targets:
    found: dict[str, Mapping[str, Any]] = {}
    for ref in args.jobs:
        found.update(await _job_target(ctx, ref))
    return found


async def _each(
    ctx: ActionContext, args: ManyJobsArgs, which: Literal["applied", "inquired", "restore"]
) -> list[Applied] | ActionError:
    done: list[Applied] = []
    for ref in args.jobs:
        if which == "restore":
            result = await restore_job(ctx, OneJob(job=ref))
        else:
            mark = MarkArgs(job=ref, on=args.on)
            handler = mark_applied_action if which == "applied" else mark_inquired_action
            result = await handler(ctx, mark)
        if isinstance(result, ActionError):
            return ActionError(result.reason, f"{ref}: {result.message}")
        done.append(result)
    return done


async def mark_applied_many(ctx: ActionContext, args: ManyJobsArgs) -> list[Applied] | ActionError:
    return await _each(ctx, args, "applied")


async def mark_inquired_many(ctx: ActionContext, args: ManyJobsArgs) -> list[Applied] | ActionError:
    return await _each(ctx, args, "inquired")


async def restore_jobs(ctx: ActionContext, args: ManyJobsArgs) -> list[Applied] | ActionError:
    return await _each(ctx, args, "restore")


# ---- searches ------------------------------------------------------------------------------


class StartSearchArgs(BaseModel):
    mode: Literal["rules_and_ai", "rules_only"] = Field(
        "rules_and_ai", description="rules_only skips the AI check of the jobs found"
    )


async def _running(ctx: ActionContext) -> SearchRunRow | None:
    return await ctx.session.scalar(
        select(SearchRunRow).where(
            SearchRunRow.finished_at.is_(None), SearchRunRow.outcome.is_(None)
        )
    )


async def _search_target(ctx: ActionContext, args: StartSearchArgs) -> Targets:
    running = await _running(ctx)
    if running is not None:  # EC-11: report it instead of starting another
        raise ActionRefusedError(
            "search_already_running",
            f"A search is already running: {running.next_index} of "
            f"{len(running.company_order)} companies read, {running.jobs_found} jobs found.",
        )
    return {"search": {"label": "a new search", "mode": args.mode}}


async def start_search_action(ctx: ActionContext, args: StartSearchArgs) -> Applied | ActionError:
    start = ctx.services.start_search
    if start is None:
        return ActionError("unavailable", "Searches can't be started from here.")
    try:
        search_run_id = await start(ctx.session, args.mode, ctx.now)
    except RulesNotApprovedError:
        return ActionError("rules_not_approved", "Approve your search rules first.")
    except SetupIncompleteError:
        return ActionError("setup_incomplete", "Finish setup before searching.")
    except SearchAlreadyRunningError:
        return ActionError("search_already_running", "A search is already running.")
    ref = str(Ref("search_run", search_run_id))
    return Applied("search_run", search_run_id, {}, {}, "Started a search.", [ref])


class RunArgs(BaseModel):
    search_run: str = Field(description="The search's ref, like search_run:<id>")


async def _run_target(ctx: ActionContext, args: RunArgs) -> Targets:
    row = await ctx.session.get(
        SearchRunRow, Ref.parse(args.search_run, expect="search_run").id, populate_existing=True
    )
    if row is None:
        return {}
    return {
        str(Ref("search_run", row.id)): {"label": "the running search", "stop": row.stop_requested}
    }


async def stop_search(ctx: ActionContext, args: RunArgs) -> Applied | ActionError:
    run_id = Ref.parse(args.search_run, expect="search_run").id
    try:
        await request_stop(SearchStore(ctx.session), run_id)
    except SearchNotRunningError:
        return ActionError("not_running", "That search is not running.")
    return Applied("search_run", run_id, {}, {"stop_requested": True}, "Asked the search to stop.")


# ---- mail ----------------------------------------------------------------------------------

MAIL_REFUSALS = {
    "not_connected": "Gmail is not connected. You can connect it in Settings → Gmail.",
    "needs_reconnect": "Gmail needs to be connected again in Settings → Gmail.",
    "search_running": "A search is running; check the mail when it ends.",
    "no_rules": "Approve your search rules first.",
}


class MailCheckArgs(BaseModel):
    reread_last_day: bool = Field(False, description="Read the last day's alert emails again")


async def _mail_target(ctx: ActionContext, args: MailCheckArgs) -> Targets:
    return {"mail": {"label": "your job-alert mail", "reread": args.reread_last_day}}


async def start_mail_check(ctx: ActionContext, args: MailCheckArgs) -> Applied | ActionError:
    start = ctx.services.start_mail_check
    if start is None:
        return ActionError("unavailable", "The mail can't be checked from here.")
    try:
        search_run_id = await start(ctx.now, args.reread_last_day)
    except CheckNotReadyError as error:
        return ActionError(
            error.reason, MAIL_REFUSALS.get(error.reason, "The mail can't be checked now.")
        )
    ref = str(Ref("search_run", search_run_id))
    return Applied(
        "search_run", search_run_id, {}, {}, "Started checking your job-alert mail.", [ref]
    )


class AddSenderArgs(BaseModel):
    address: str = Field(min_length=3, max_length=254, description="An alert sender's address")


class SenderArgs(BaseModel):
    sender: str = Field(description="The sender's ref, like sender:<id>")


class SwitchSenderArgs(SenderArgs):
    enabled: bool


async def _sender_target(ctx: ActionContext, args: SenderArgs) -> Targets:
    row = await ctx.session.get(
        MailSenderRow, Ref.parse(args.sender, expect="sender").id, populate_existing=True
    )
    if row is None:
        return {}
    return {str(Ref("sender", row.id)): {"label": f"{row.site} alerts", "enabled": row.enabled}}


async def _new_sender_target(ctx: ActionContext, args: AddSenderArgs) -> Targets:
    return {"sender:new": {"label": bounded(args.address, 254).text}}


async def add_mail_sender(ctx: ActionContext, args: AddSenderArgs) -> Applied | ActionError:
    try:
        row = await SendersRepo(ctx.session).add_custom(args.address)
    except SenderError as error:
        return ActionError("invalid_address", str(error))
    except SenderExistsError as error:
        return ActionError("sender_exists", str(error))
    return Applied("sender", row.id, {}, {"enabled": True}, "Added the alert sender.")


async def switch_mail_sender(ctx: ActionContext, args: SwitchSenderArgs) -> Applied | ActionError:
    sender_id = Ref.parse(args.sender, expect="sender").id
    repo = SendersRepo(ctx.session)
    row = await repo.get(sender_id)
    if row is None:
        return ActionError("not_found", "That sender is not in HireTitan.")
    before = {"enabled": row.enabled}
    await repo.set_enabled(sender_id, args.enabled)
    word = "on" if args.enabled else "off"
    return Applied(
        "sender", sender_id, before, {"enabled": args.enabled}, f"Turned {row.site} alerts {word}."
    )


async def remove_mail_sender(ctx: ActionContext, args: SenderArgs) -> Applied | ActionError:
    sender_id = Ref.parse(args.sender, expect="sender").id
    repo = SendersRepo(ctx.session)
    if await repo.get(sender_id) is None:
        return ActionError("not_found", "That sender is not in HireTitan.")
    try:
        await repo.remove(sender_id)
    except BuiltInSenderError as error:
        return ActionError("built_in", str(error))
    return Applied("sender", sender_id, {}, {}, "Removed the alert sender.")


def _risky(
    name: str,
    description: str,
    args: type[BaseModel],
    handler: Any,
    targets: Any,
    title: str,
    mirrors: tuple[str, ...],
    **extra: Any,
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
        **extra,
    )


CHANGES: tuple[ActionSpec, ...] = (
    _risky(
        "delete_job",
        "Delete one job (it can't be added again).",
        OneJob,
        delete_job_action,
        _one_job,
        "Delete",
        ("DELETE /jobs/{job_id}",),
    ),
    _risky(
        "recheck_job",
        "Ask the AI to check a job it has not checked.",
        OneJob,
        recheck_job,
        _one_job,
        "Check with the AI",
        ("POST /jobs/{job_id}/recheck",),
    ),
    _risky(
        "merge_duplicate",
        "Merge a possible-duplicate pair into one job.",
        PairArgs,
        merge_duplicate,
        _pair_target,
        "Merge",
        ("POST /jobs/duplicates/{pair_id}/merge",),
    ),
    _risky(
        "dismiss_duplicate",
        "Keep a possible-duplicate pair as two jobs.",
        PairArgs,
        dismiss_duplicate,
        _pair_target,
        "Keep apart",
        ("POST /jobs/duplicates/{pair_id}/dismiss",),
    ),
    _risky(
        "mark_applied_many",
        "Mark several jobs (up to 25) as applied.",
        ManyJobsArgs,
        mark_applied_many,
        _many_targets,
        "Mark as applied",
        (),
        undo=put_status_back,
        current=current_status,
        editable=("on",),
    ),
    _risky(
        "mark_inquired_many",
        "Mark several jobs (up to 25) as inquired.",
        ManyJobsArgs,
        mark_inquired_many,
        _many_targets,
        "Mark as inquired",
        (),
        undo=put_status_back,
        current=current_status,
        editable=("on",),
    ),
    _risky(
        "restore_jobs",
        "Bring several hidden jobs (up to 25) back to Explore.",
        ManyJobsArgs,
        restore_jobs,
        _many_targets,
        "Bring back to Explore",
        (),
        undo=hide_again,
    ),
    _risky(
        "start_search",
        "Start a search now. If one is running, say how far it got instead.",
        StartSearchArgs,
        start_search_action,
        _search_target,
        "Start",
        ("POST /search/runs",),
        editable=("mode",),
    ),
    _risky(
        "stop_search",
        "Stop the running search.",
        RunArgs,
        stop_search,
        _run_target,
        "Stop",
        ("POST /search/runs/{search_run_id}/stop",),
    ),
    _risky(
        "start_mail_check",
        "Check the job-alert mail now (or read the last day again).",
        MailCheckArgs,
        start_mail_check,
        _mail_target,
        "Check",
        ("POST /mail/checks",),
        editable=("reread_last_day",),
    ),
    _risky(
        "add_mail_sender",
        "Add a job-alert sender address.",
        AddSenderArgs,
        add_mail_sender,
        _new_sender_target,
        "Add the alert sender",
        ("POST /mail/senders",),
    ),
    _risky(
        "switch_mail_sender",
        "Turn a job-alert sender on or off.",
        SwitchSenderArgs,
        switch_mail_sender,
        _sender_target,
        "Change",
        ("PATCH /mail/senders/{sender_id}",),
        editable=("enabled",),
    ),
    _risky(
        "remove_mail_sender",
        "Remove a job-alert sender you added.",
        SenderArgs,
        remove_mail_sender,
        _sender_target,
        "Remove",
        ("DELETE /mail/senders/{sender_id}",),
    ),
)
