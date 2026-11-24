"""Mikasa's actions on jobs (002m contracts/actions.md, "Jobs and search results").

Read actions here build their answers from the job rows directly: only bounded fields, never a
description (the stored ``job_keywords`` stand in for it, research R4).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Date, and_, cast, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, ReadResult
from hiretitan.actions.text import bounded
from hiretitan.drafts.infra.repos import KeywordsRepo
from hiretitan.search.domain.normalize import canonical_url
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import JobRow, JobSourceRow, RelevanceDecisionRow

NOT_FOUND = ActionError("not_found", "That job is not in HireTitan.")


def _day(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return (value.date() if isinstance(value, datetime) else value).isoformat()


def job_ref(job_id: UUID) -> str:
    return str(Ref("job", job_id))


def _job_fields(row: JobRow, hidden_reason: str | None = None) -> dict[str, Any]:
    title = bounded(row.title)
    company = bounded(row.company_name)
    item: dict[str, Any] = {
        "ref": job_ref(row.id),
        "title": title.text,
        "company": company.text,
        "city": bounded(row.city, 80).text or None,
        "work_mode": row.work_mode,
        "state": row.state,
        "first_seen": _day(row.first_seen_at),
        "posted": _day(row.posted_at),
        "applied_on": _day(row.applied_on),
        "inquired_on": _day(row.inquired_on),
        "flagged": title.flagged or company.flagged or bool(row.injection_flags),
    }
    if hidden_reason is not None:
        item["hidden_reason"] = bounded(hidden_reason).text
    return item


async def _load(ctx: ActionContext, ref: str) -> JobRow | None:
    job_id = Ref.parse(ref, expect="job").id
    row = await ctx.session.get(JobRow, job_id)
    return None if row is None or row.state == "deleted" else row


async def _reasons(ctx: ActionContext, rows: list[JobRow]) -> dict[UUID, str]:
    hidden = [row.id for row in rows if row.state == "skipped"]
    if not hidden:
        return {}
    found = await ctx.session.execute(
        select(RelevanceDecisionRow.job_id, RelevanceDecisionRow.reason).where(
            RelevanceDecisionRow.job_id.in_(hidden), RelevanceDecisionRow.is_current
        )
    )
    return {job_id: reason for job_id, reason in found.all()}


# ---- search_jobs ---------------------------------------------------------------------------


class SearchJobsArgs(BaseModel):
    list: Literal["explore", "pipeline", "hidden"] = Field(
        "explore",
        description="explore: jobs to look at; pipeline: applied or inquired; hidden: hidden by "
        "the person's rules",
    )
    state: Literal["applied", "inquired"] | None = Field(
        None, description="Only with list=pipeline: just applied or just inquired jobs"
    )
    company: str | None = Field(None, max_length=120, description="Part of the company name")
    title: str | None = Field(None, max_length=120, description="Part of the job title")
    since: date | None = Field(
        None, description="From this day: when the job was found, or when it was marked"
    )
    until: date | None = Field(None, description="Up to and including this day")
    limit: int = Field(20, ge=1, le=50)


async def search_jobs(ctx: ActionContext, args: SearchJobsArgs) -> ReadResult:
    marked = func.coalesce(JobRow.applied_on, JobRow.inquired_on)
    conditions: list[ColumnElement[bool]] = []
    if args.list == "pipeline":
        states = (args.state,) if args.state else ("applied", "inquired")
        conditions.append(JobRow.state.in_(states))
        day: Any = marked
        order: list[Any] = [marked.desc(), JobRow.id]
    else:
        conditions.append(JobRow.state == ("skipped" if args.list == "hidden" else "explore"))
        day = cast(JobRow.first_seen_at, Date)
        order = [JobRow.sort_key.desc(), JobRow.id]
    if args.company:
        conditions.append(JobRow.company_name.ilike(f"%{_like(args.company)}%", escape="\\"))
    if args.title:
        conditions.append(JobRow.title.ilike(f"%{_like(args.title)}%", escape="\\"))
    if args.since:
        conditions.append(day >= args.since)
    if args.until:
        conditions.append(day <= args.until)
    where = and_(*conditions)
    total = await ctx.session.scalar(select(func.count()).select_from(JobRow).where(where)) or 0
    rows = list(
        await ctx.session.scalars(select(JobRow).where(where).order_by(*order).limit(args.limit))
    )
    reasons = await _reasons(ctx, rows)
    return ReadResult(
        items=[_job_fields(row, reasons.get(row.id)) for row in rows],
        total=total,
        truncated=total > len(rows),
    )


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---- get_job -------------------------------------------------------------------------------


class JobArgs(BaseModel):
    job: str = Field(description="The job's ref, like job:<id>")


async def get_job(ctx: ActionContext, args: JobArgs) -> ReadResult | ActionError:
    row = await _load(ctx, args.job)
    if row is None:
        return NOT_FOUND
    item = _job_fields(row, (await _reasons(ctx, [row])).get(row.id))
    sources = await ctx.session.scalars(
        select(JobSourceRow.kind).where(JobSourceRow.job_id == row.id).distinct()
    )
    item["sources"] = sorted(sources)
    item["link"] = bounded(row.canonical_url, 500).text or None
    item["has_description"] = bool(row.description.strip())
    keywords = await KeywordsRepo(ctx.session).get(row.id)
    if keywords is not None:
        summary = bounded(keywords.role_summary, 160)
        item["role_summary"] = summary.text
        item["keywords"] = [bounded(k, 60).text for k in keywords.keywords]
        item["must_have"] = [bounded(k, 60).text for k in keywords.must_have]
        item["flagged"] = item["flagged"] or summary.flagged or bool(keywords.injection_signals)
    return ReadResult(items=[item], total=1)


# ---- find_job_by_link ----------------------------------------------------------------------


class LinkArgs(BaseModel):
    url: str = Field(max_length=2000, description="A job link the person gave")


async def find_job_by_link(ctx: ActionContext, args: LinkArgs) -> ReadResult:
    """Look the link up; HireTitan never opens it (constitution VII, FR-008)."""
    canonical = canonical_url(args.url)
    row = None
    if canonical:
        row = await ctx.session.scalar(
            select(JobRow).where(
                or_(
                    JobRow.canonical_url == canonical,
                    JobRow.id.in_(
                        select(JobSourceRow.job_id).where(JobSourceRow.url == args.url.strip())
                    ),
                )
            )
        )
    if row is None:
        return ReadResult(items=[{"found": False, "url": bounded(args.url, 500).text}], total=0)
    if row.state == "deleted":
        return ReadResult(
            items=[{"found": False, "deleted": True, "url": bounded(args.url, 500).text}], total=0
        )
    return ReadResult(items=[{"found": True, **_job_fields(row)}], total=1)


# ---- get_pipeline_summary ------------------------------------------------------------------


class NoArgs(BaseModel):
    pass


async def get_pipeline_summary(ctx: ActionContext, args: NoArgs) -> ReadResult:
    """Counts only: the rounds' contents stay private (002e FR-010)."""
    counts = await InterviewsRepo(ctx.session).status_counts()
    return ReadResult(items=[{**counts, "total": sum(counts.values())}], total=1)


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="search_jobs",
        description="Find the person's jobs: in Explore, in the pipeline (applied or inquired), "
        "or hidden by their rules. Newest first. Returns refs and short fields.",
        args=SearchJobsArgs,
        kind="read",
        handler=search_jobs,
        mirrors=("GET /jobs",),
    ),
    ActionSpec(
        name="get_job",
        description="One job's details: title, company, place, state, dates, sources, link, "
        "and what its description asks for (keywords), when HireTitan has read it.",
        args=JobArgs,
        kind="read",
        handler=get_job,
        mirrors=("GET /jobs/{job_id}",),
    ),
    ActionSpec(
        name="find_job_by_link",
        description="Check whether a job link is already in HireTitan. Never opens the link.",
        args=LinkArgs,
        kind="read",
        handler=find_job_by_link,
    ),
    ActionSpec(
        name="get_pipeline_summary",
        description="How many pipeline jobs are in each status (inquired, applied, interview "
        "scheduled, cleared, failed).",
        args=NoArgs,
        kind="read",
        handler=get_pipeline_summary,
        mirrors=("GET /pipeline/summary",),
    ),
)
