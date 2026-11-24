"""Mikasa's actions on interview details and the resume used (002m contracts/actions.md).

Private (002e FR-010, 002f FR-013, research R5): rounds, questions, answers, feedback, the
pipeline contact and resume files reach the model only as refs with labels built from the job's
title and company. Sorting ("the next interview") happens here, so the model needs no dates.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from hiretitan.actions.refs import (
    Ref,
    label_interview,
    label_question,
    label_resume_file,
    label_round,
)
from hiretitan.actions.spec import (
    ActionContext,
    ActionError,
    ActionSpec,
    PrivateItem,
    PrivateResult,
)
from hiretitan.actions.text import bounded
from hiretitan.profile.infra.repos import ResumeFilesRepo
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import InterviewRoundRow, JobRow

JOB_NOT_FOUND = ActionError("not_found", "That job is not in HireTitan.")


def _job_label(row: JobRow) -> tuple[str, str]:
    return bounded(row.title).text, bounded(row.company_name).text


def _numbered(label: str, n: int, total: int) -> str:
    return f"{label} ({n} of {total})" if total > 1 else label


class JobArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")


async def get_interview(ctx: ActionContext, args: JobArgs) -> PrivateResult | ActionError:
    job = await ctx.session.get(JobRow, Ref.parse(args.job, expect="job").id)
    if job is None or job.state == "deleted":
        return JOB_NOT_FOUND
    title, company = _job_label(job)
    data = await InterviewsRepo(ctx.session).details(job.id)
    items: list[PrivateItem] = []
    if data.details is not None:
        items.append(
            PrivateItem(ref=str(Ref("interview", job.id)), label=label_interview(title, company))
        )
    for n, entry in enumerate(data.rounds, start=1):
        items.append(
            PrivateItem(
                ref=str(Ref("round", entry.round.id)),
                label=_numbered(label_round(title, company), n, len(data.rounds)),
            )
        )
        for question in entry.questions:
            items.append(
                PrivateItem(
                    ref=str(Ref("question", question.id)), label=label_question(title, company)
                )
            )
    return PrivateResult(items=items, total=len(items))


class ListRoundsArgs(BaseModel):
    upcoming: bool = Field(True, description="Only scheduled rounds from now on, soonest first")
    job: str | None = Field(None, description="Only this job's rounds (a job ref)")
    limit: int = Field(10, ge=1, le=30)


async def list_rounds(ctx: ActionContext, args: ListRoundsArgs) -> PrivateResult:
    query = select(InterviewRoundRow, JobRow).join(JobRow, JobRow.id == InterviewRoundRow.job_id)
    query = query.where(JobRow.state.not_in(("deleted", "staged")))
    if args.job:
        query = query.where(JobRow.id == Ref.parse(args.job, expect="job").id)
    if args.upcoming:
        query = query.where(
            InterviewRoundRow.state == "scheduled", InterviewRoundRow.scheduled_at >= ctx.now
        ).order_by(InterviewRoundRow.scheduled_at, InterviewRoundRow.id)
    else:
        query = query.order_by(InterviewRoundRow.scheduled_at.desc().nulls_last())
    rows = (await ctx.session.execute(query.limit(args.limit))).all()
    items = []
    for round_row, job in rows:
        title, company = _job_label(job)
        items.append(
            PrivateItem(ref=str(Ref("round", round_row.id)), label=label_round(title, company))
        )
    return PrivateResult(items=items, total=len(items))


class NoArgs(BaseModel):
    pass


async def list_resume_files(ctx: ActionContext, args: NoArgs) -> PrivateResult:
    files = await ResumeFilesRepo(ctx.session).list()
    return PrivateResult(
        items=[
            PrivateItem(
                ref=str(Ref("resume_file", f.id)),
                label=_numbered(label_resume_file(), n, len(files)),
            )
            for n, f in enumerate(files, start=1)
        ],
        total=len(files),
    )


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="get_interview",
        description="A pipeline job's interview details (contact, source, rounds, questions), "
        "as refs the app shows. You never see what they say.",
        args=JobArgs,
        kind="read",
        private=True,
        handler=get_interview,
        mirrors=("GET /jobs/{job_id}/interview",),
    ),
    ActionSpec(
        name="list_rounds",
        description="Interview rounds as refs, soonest first: by default the scheduled ones still "
        "to come. The app shows their dates and details.",
        args=ListRoundsArgs,
        kind="read",
        private=True,
        handler=list_rounds,
    ),
    ActionSpec(
        name="list_resume_files",
        description="The person's stored resume files, as refs the app shows by name.",
        args=NoArgs,
        kind="read",
        private=True,
        handler=list_resume_files,
        mirrors=("GET /resumes", "GET /pipeline/resumes"),
    ),
)
