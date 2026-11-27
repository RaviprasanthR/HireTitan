"""Mikasa's actions on searches (002m contracts/actions.md, "Searches and mail")."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, ReadResult
from hiretitan.actions.text import bounded
from hiretitan.search.infra.models import SearchRunRow
from hiretitan.search.infra.repos import SearchRunsRepo

NOT_FOUND = ActionError("not_found", "That search is not in HireTitan.")


def run_fields(row: SearchRunRow) -> dict[str, Any]:
    return {
        "ref": str(Ref("search_run", row.id)),
        "mode": "mail_check" if row.mode == "mail_alerts" else "search",
        "running": row.finished_at is None and row.outcome is None,
        "outcome": row.outcome,
        "stop_message": bounded(row.stop_message).text or None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "companies_total": len(row.company_order),
        "companies_read": row.next_index,
        "jobs_found": row.jobs_found,
        "skipped_by_rules": row.skipped_by_rules,
        "kept": row.kept,
        "added": row.added,
        "merged": row.merged,
        "not_checked_by_ai": row.not_checked_by_ai,
    }


class NoArgs(BaseModel):
    pass


async def get_latest_search(ctx: ActionContext, args: NoArgs) -> ReadResult:
    row = await SearchRunsRepo(ctx.session).latest()
    if row is None:
        return ReadResult(items=[], total=0)
    return ReadResult(items=[run_fields(row)], total=1)


class ListRunsArgs(BaseModel):
    limit: int = Field(10, ge=1, le=30)


async def list_search_runs(ctx: ActionContext, args: ListRunsArgs) -> ReadResult:
    rows = list(
        await ctx.session.scalars(
            select(SearchRunRow)
            .order_by(SearchRunRow.created_at.desc(), SearchRunRow.id.desc())
            .limit(args.limit + 1)
        )
    )
    shown = rows[: args.limit]
    return ReadResult(
        items=[run_fields(row) for row in shown],
        total=len(shown),
        truncated=len(rows) > args.limit,
    )


class RunArgs(BaseModel):
    search_run: str = Field(description="The search's ref, like search_run:<id>")


async def get_search_run(ctx: ActionContext, args: RunArgs) -> ReadResult | ActionError:
    row = await SearchRunsRepo(ctx.session).get(Ref.parse(args.search_run, expect="search_run").id)
    if row is None:
        return NOT_FOUND
    return ReadResult(items=[run_fields(row)], total=1)


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="get_latest_search",
        description="The last search or job-alert mail check: whether it is running, and how "
        "many jobs it found, kept and added.",
        args=NoArgs,
        kind="read",
        handler=get_latest_search,
        mirrors=("GET /search/latest",),
    ),
    ActionSpec(
        name="list_search_runs",
        description="Past searches and mail checks, newest first.",
        args=ListRunsArgs,
        kind="read",
        handler=list_search_runs,
        mirrors=("GET /search/runs",),
    ),
    ActionSpec(
        name="get_search_run",
        description="One search or mail check by its ref.",
        args=RunArgs,
        kind="read",
        handler=get_search_run,
        mirrors=("GET /search/runs/{search_run_id}",),
    ),
)
