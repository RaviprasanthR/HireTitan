"""Mikasa's reads of review items and settings (002m contracts/actions.md).

Never the AI key itself; only whether it works, and the provider's own message when it does not.
"""

from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel
from sqlalchemy import select

from hiretitan.actions.spec import ActionContext, ActionSpec, ReadResult
from hiretitan.actions.text import bounded
from hiretitan.platform.llm.infra.models import ProviderStatusRow
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.setup.application.review_items import build_review_items
from hiretitan.setup.domain.checklist import build_checklist
from hiretitan.setup_wiring import RepoFacts


class NoArgs(BaseModel):
    pass


async def list_review_items(ctx: ActionContext, args: NoArgs) -> ReadResult:
    runs = await RunsRepo(ctx.session).list_by_status(RunStatus.awaiting_review, RunStatus.paused)
    items = await build_review_items(runs, RepoFacts(ctx.session))
    return ReadResult(
        items=[{"kind": item.kind, "title": item.title, "page": item.target} for item in items],
        total=len(items),
    )


async def get_settings(ctx: ActionContext, args: NoArgs) -> ReadResult:
    provider = await ctx.session.scalar(select(ProviderStatusRow).limit(1))
    status = provider.status if provider is not None else "unknown"
    facts = RepoFacts(ctx.session)
    checklist = build_checklist(
        key_status=status,
        resume_uploaded=await facts.resume_uploaded(),
        profile_confirmed=await facts.profile_confirmed(),
        preferences_saved=await facts.preferences_saved(),
        rules_approved=await facts.rules_approved(),
        searched_once=await facts.searched_once(),
    )
    return ReadResult(
        items=[
            {
                "ai_status": status,
                "ai_message": bounded(provider.message).text or None if provider else None,
                "checklist": asdict(checklist),
                "page": "/settings",
            }
        ],
        total=1,
    )


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="list_review_items",
        description="Things waiting for the person: a profile review, a paused import, "
        "suspicious text to decide on. Each with the page that handles it.",
        args=NoArgs,
        kind="read",
        handler=list_review_items,
        mirrors=("GET /review-items",),
    ),
    ActionSpec(
        name="get_settings",
        description="Whether the AI key works (never the key) and the setup checklist.",
        args=NoArgs,
        kind="read",
        handler=get_settings,
        mirrors=("GET /status", "GET /onboarding"),
    ),
)
