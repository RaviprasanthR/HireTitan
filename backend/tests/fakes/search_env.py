"""Shared helpers for the W3 graph tests: an environment with a fake scanner and a fake LLM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.career_ops import FakeCareerOps

import hiretitan.prompts as hiretitan_prompts
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.application.ports import BoardRef, Posting
from hiretitan.search.domain.cards import ProfileCard
from hiretitan.search.domain.rules import LocationRule, RuleItem, SearchRules
from hiretitan.search.domain.rules_serialization import rules_to_dict
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.repos import CompaniesRepo, RuleSetsRepo, SearchRunsRepo
from hiretitan.search.workflow.graph import SearchDeps, run_search
from hiretitan.search.workflow.judge import JudgeDeps

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)

RULES = SearchRules(
    title_words=(RuleItem("Backend Engineer", "user"),),
    blocked_locations=(LocationRule("Chennai", "IN", "user"),),
    max_age_days=30,
)


@dataclass
class Env:
    sessions: async_sessionmaker[AsyncSession]
    career_ops: FakeCareerOps
    deps: SearchDeps
    published: list[tuple[str, dict[str, object]]]
    llm: FakeLlm


async def add_company(env: Env, name: str, **fields: object) -> BoardRef:
    async with env.sessions() as session:
        row = await CompaniesRepo(session).add(
            name=name,
            origin="user",
            resolution="verified",
            ats_vendor="lever",
            board_id=name.lower(),
            **fields,
        )
        await session.commit()
        return BoardRef(row.id, "lever", name.lower())


def posting(title: str, company: str = "acme", **changes: object) -> Posting:
    base = {
        "title": title,
        "url": f"https://jobs.example.com/{company}/{title.replace(' ', '-')}",
        "location": "Pune, India",
        "posted_at": NOW - timedelta(days=2),
        "description": "Build things with Python.",
        "requisition_id": None,
    }
    return Posting(**{**base, **changes})  # type: ignore[arg-type]


async def new_search(
    env: Env,
    *,
    order: list[UUID] | None = None,
    rules: SearchRules = RULES,
    mode: str = "rules_only",
) -> UUID:
    """Approve rules and create a queued search run; returns the workflow run id."""
    async with env.sessions() as session:
        rule_sets = RuleSetsRepo(session)
        rule_set = await rule_sets.approve((await rule_sets.propose(rules_to_dict(rules), {})).id)
        workflow = await RunsRepo(session).create("job_search")
        await SearchRunsRepo(session).create(
            workflow_run_id=workflow.id,
            rule_set_id=rule_set.id,
            mode=mode,
            company_order=order or [],
            started_at=NOW,
        )
        await session.commit()
        return workflow.id


async def complete(env: Env, workflow_run_id: UUID) -> None:
    """What the worker does when the graph ends, so the next search may start."""
    async with env.sessions() as session:
        runs = RunsRepo(session)
        await runs.transition(workflow_run_id, RunStatus.running)
        await runs.transition(workflow_run_id, RunStatus.done)
        await session.commit()


async def go(env: Env, workflow_run_id: UUID) -> None:
    await run_search(env.deps, workflow_run_id)
    await complete(env, workflow_run_id)


async def titles(env: Env, state: str) -> set[str]:
    async with env.sessions() as session:
        rows = await session.scalars(select(JobRow).where(JobRow.state == state))
        return {r.title for r in rows}


CARD = ProfileCard(
    target_roles=("Backend Engineer",),
    seniority=("junior",),
    years_experience=Decimal(2),
    key_skills=("Python", "FastAPI"),
    preferred_locations=("Pune",),
    work_modes=("remote",),
)


def make_env(sessions: async_sessionmaker[AsyncSession]) -> Env:
    career_ops = FakeCareerOps()
    llm = FakeLlm()
    published: list[tuple[str, dict[str, object]]] = []

    async def publish(event: str, data: dict[str, object]) -> None:
        published.append((event, data))

    async def card() -> ProfileCard | None:
        return CARD

    deps = SearchDeps(
        sessions=sessions,
        career_ops=career_ops,
        clock=FakeClock(NOW),
        synonyms={},
        publish=publish,
        judge=JudgeDeps(
            sessions=sessions,
            llm=llm,
            profile_card=card,
            prompts=PromptRegistry(Path(hiretitan_prompts.__file__).parent),
        ),
    )
    return Env(sessions, career_ops, deps, published, llm)
