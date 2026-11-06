"""T030: the W3 graph without the AI step (US1, FR-010a, FR-011, FR-026)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.career_ops import FakeCareerOps

from hiretitan.platform.clock import FakeClock
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.application.ports import BoardRef, Posting, ScanError, ScanOk
from hiretitan.search.domain.rules import LocationRule, RuleItem, SearchRules
from hiretitan.search.domain.rules_serialization import rules_to_dict
from hiretitan.search.infra.models import (
    JobRow,
    RelevanceDecisionRow,
    SearchRunCompanyRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, RuleSetsRepo, SearchRunsRepo
from hiretitan.search.workflow.graph import SearchDeps, run_search

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


@pytest.fixture
def env(sessions: async_sessionmaker[AsyncSession]) -> Env:
    career_ops = FakeCareerOps()
    published: list[tuple[str, dict[str, object]]] = []

    async def publish(event: str, data: dict[str, object]) -> None:
        published.append((event, data))

    deps = SearchDeps(
        sessions=sessions,
        career_ops=career_ops,
        clock=FakeClock(NOW),
        synonyms={},
        publish=publish,
    )
    return Env(sessions, career_ops, deps, published)


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
    env: Env, *, order: list[UUID] | None = None, rules: SearchRules = RULES
) -> UUID:
    """Approve rules and create a queued search run; returns the workflow run id."""
    async with env.sessions() as session:
        rule_sets = RuleSetsRepo(session)
        rule_set = await rule_sets.approve((await rule_sets.propose(rules_to_dict(rules), {})).id)
        workflow = await RunsRepo(session).create("job_search")
        await SearchRunsRepo(session).create(
            workflow_run_id=workflow.id,
            rule_set_id=rule_set.id,
            mode="rules_only",
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


async def test_US1_AS1_relevant_jobs_added_after_each_batch(env: Env) -> None:
    companies = [await add_company(env, f"C{i}") for i in range(9)]  # 8 + 1: two batches
    for ref in companies:
        env.career_ops.script(ref, ScanOk([posting("Backend Engineer", ref.board_id)]))
    run_id = await new_search(env)

    await go(env, run_id)

    assert len(env.career_ops.scan_calls) == 2
    assert [len(c) for c in env.career_ops.scan_calls] == [8, 1]
    assert len(await titles(env, "explore")) == 1  # same title in every company...
    async with env.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(JobRow)) == 9
        run = await SearchRunsRepo(session).latest()
    assert run is not None
    assert (run.batches_done, run.jobs_found, run.added, run.outcome) == (2, 9, 9, "finished")
    batch_events = [d for e, d in env.published if e == "search.batch_done"]
    assert [e["batches_done"] for e in batch_events] == [1, 2]
    assert env.published[-1][0] == "search.finished"


async def test_FR011_failing_company_does_not_stop_others(env: Env) -> None:
    good = await add_company(env, "Good")
    bad = await add_company(env, "Bad")
    env.career_ops.script(good, ScanOk([posting("Backend Engineer", "good")]))
    env.career_ops.script(bad, ScanError("board timed out"))
    run_id = await new_search(env)

    await go(env, run_id)

    async with env.sessions() as session:
        results = {
            r.company_id: (r.result, r.error)
            for r in await session.scalars(select(SearchRunCompanyRow))
        }
        run = await SearchRunsRepo(session).latest()
        bad_company = await CompaniesRepo(session).get(bad.company_id)
    assert results[good.company_id] == ("ok", None)
    assert results[bad.company_id] == ("failed", "board timed out")
    assert run is not None
    assert (run.added, run.outcome) == (1, "finished")
    assert bad_company is not None
    assert (bad_company.last_check_result, bad_company.last_check_error) == (
        "failed",
        "board timed out",
    )
    assert bad_company.last_checked_at == NOW


async def test_US1_AS6_seen_again_job_keeps_state_and_is_not_duplicated(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env))
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow))).one()
        job.state = "skipped"  # the person's choice must survive the next search
        job.restored = False
        await session.commit()

    env.career_ops.script(
        ref,
        ScanOk(
            [
                posting(
                    "Backend Engineer",
                    url="https://jobs.example.com/acme/Backend-Engineer?utm_source=x",
                )
            ]
        ),
    )
    await go(env, await new_search(env))

    async with env.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(JobRow)) == 1
        job = (await session.scalars(select(JobRow))).one()
        decisions = await session.scalar(select(func.count()).select_from(RelevanceDecisionRow))
        run = await SearchRunsRepo(session).latest()
    assert job.state == "skipped"
    assert decisions == 1
    assert run is not None
    assert (run.merged, run.added) == (1, 0)


async def test_FR010a_next_search_continues_with_unread_companies(env: Env) -> None:
    refs = [await add_company(env, f"C{i}") for i in range(10)]
    for ref in refs:
        env.career_ops.script(ref, ScanOk([posting("Backend Engineer", ref.board_id)]))
    first = await new_search(env, order=[r.company_id for r in refs])
    async with env.sessions() as session:  # a search that ended early after the first 8
        run = await SearchRunsRepo(session).latest()
        assert run is not None
        await session.execute(
            update(SearchRunRow).where(SearchRunRow.id == run.id).values(next_index=8)
        )
        await SearchRunsRepo(session).finish(
            run.id, outcome="stopped_by_user", finished_at=NOW, stop_message=None
        )
        await session.commit()
    await complete(env, first)
    async with env.sessions() as session:  # the first 8 were read recently
        for ref in refs[:8]:
            await CompaniesRepo(session).set_fields(ref.company_id, last_checked_at=NOW)
        await session.commit()

    second = await new_search(env)  # plans its own order
    env.career_ops.scan_calls.clear()
    await go(env, second)

    first_batch = {ref.company_id for ref in env.career_ops.scan_calls[0]}
    assert {refs[8].company_id, refs[9].company_id} <= first_batch


async def test_US1_AS3_skipped_jobs_kept_with_reason(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(
        ref,
        ScanOk(
            [
                posting("Backend Engineer"),
                posting("Sales Executive"),
                posting("Backend Engineer II", location="Chennai, India"),
            ]
        ),
    )
    await go(env, await new_search(env))

    assert await titles(env, "explore") == {"Backend Engineer"}
    assert await titles(env, "skipped") == {"Sales Executive", "Backend Engineer II"}
    async with env.sessions() as session:
        reasons = {
            r.reason
            for r in await session.scalars(
                select(RelevanceDecisionRow).where(RelevanceDecisionRow.outcome == "skipped")
            )
        }
        run = await SearchRunsRepo(session).latest()
    assert reasons == {
        "title matches none of your roles",
        "location Chennai is in your blocked list",
    }
    assert run is not None
    assert run.skipped_by_rules == 2
