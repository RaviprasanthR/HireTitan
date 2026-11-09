"""T031: the ``judge_relevance`` step of the W3 graph (US1, FR-026, FR-028, FR-035a)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.platform.llm.port import AiUnavailable, LlmRequest
from hiretitan.search.application.ports import BoardRef, ScanOk
from hiretitan.search.infra.models import JobRow, RelevanceDecisionRow, SearchRunRow
from hiretitan.search.workflow.graph import FALLBACK_REASON

TITLES = ("Backend Engineer", "Backend Engineer II", "Backend Engineer III")
TASK = "judge_relevance"


def answer(*pairs: tuple[str, bool, str]) -> dict[str, Any]:
    return {"decisions": [{"ref": r, "relevant": ok, "reason": why} for r, ok, why in pairs]}


async def scan_titles(env: Env, titles: tuple[str, ...] | list[str]) -> BoardRef:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting(t) for t in titles]))
    return ref


async def decisions(env: Env) -> dict[str, RelevanceDecisionRow]:
    async with env.sessions() as session:
        jobs = {j.id: j.title for j in await session.scalars(select(JobRow))}
        rows = await session.scalars(
            select(RelevanceDecisionRow).where(RelevanceDecisionRow.is_current)
        )
        return {jobs[r.job_id]: r for r in rows}


async def states(env: Env) -> dict[str, str]:
    async with env.sessions() as session:
        return {j.title: j.state for j in await session.scalars(select(JobRow))}


async def test_US1_AS2_ai_reason_shown_with_job(env: Env) -> None:
    await scan_titles(env, TITLES[:2])
    env.llm.add(answer(("j1", True, "Python backend role"), ("j2", False, "Needs ten years")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    found = await decisions(env)
    kept = found["Backend Engineer"]
    assert (kept.outcome, kept.decided_by, kept.reason) == ("shown", "ai", "Python backend role")
    assert (kept.prompt_name, kept.prompt_version) == (TASK, "2")
    assert kept.llm_call_id is not None
    assert kept.provider
    assert kept.model
    assert (found["Backend Engineer II"].outcome, found["Backend Engineer II"].decided_by) == (
        "skipped",
        "ai",
    )
    assert await states(env) == {"Backend Engineer": "explore", "Backend Engineer II": "skipped"}
    async with env.sessions() as session:
        run = (await session.scalars(select(SearchRunRow))).one()
    assert (run.judged_by_ai, run.kept) == (2, 1)


async def test_FR023_ai_not_relevant_is_skipped_with_reason(env: Env) -> None:
    await scan_titles(env, TITLES[:1])
    env.llm.add(answer(("j1", False, "Mostly frontend work")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    row = (await decisions(env))["Backend Engineer"]
    assert (row.outcome, row.reason) == ("skipped", "Mostly frontend work")
    assert await states(env) == {"Backend Engineer": "skipped"}


async def test_FR026_judged_job_not_sent_again(env: Env) -> None:
    ref = await scan_titles(env, TITLES[:1])
    env.llm.add(answer(("j1", True, "Fits")))
    await go(env, await new_search(env, mode="rules_and_ai"))
    assert len(env.llm.calls) == 1

    env.career_ops.script(ref, ScanOk([posting(TITLES[0])]))
    await go(env, await new_search(env, mode="rules_and_ai"))

    assert len(env.llm.calls) == 1  # the same job is not judged again


async def test_FR028_unusable_answer_falls_back_to_rules(env: Env) -> None:
    await scan_titles(env, TITLES[:2])
    bad = answer(("j1", True, "ok"))  # j2 is missing: one repair is asked, then it gives up
    env.llm.add(bad, bad)

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert len(env.llm.calls) == 2  # first try + one repair
    found = await decisions(env)
    for title in TITLES[:2]:
        assert (found[title].decided_by, found[title].reason) == (
            "rules_only_fallback",
            FALLBACK_REASON,
        )
    assert set((await states(env)).values()) == {"explore"}


async def test_US1_AS7_no_key_runs_rules_only(env: Env) -> None:
    await scan_titles(env, TITLES[:2])

    async def no_key(_: LlmRequest[Any]) -> Any:
        raise AiUnavailable("key_missing")

    env.llm.generate = no_key  # type: ignore[method-assign,assignment]

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert {r.decided_by for r in (await decisions(env)).values()} == {"rules_only_fallback"}
    assert set((await states(env)).values()) == {"explore"}


async def test_US1_AS7_rules_only_mode_makes_no_ai_call(env: Env) -> None:
    await scan_titles(env, TITLES[:2])

    await go(env, await new_search(env, mode="rules_only"))

    assert env.llm.calls == []
    assert {r.decided_by for r in (await decisions(env)).values()} == {"rules_only_fallback"}


async def test_FR035a_calls_are_batched_by_10(env: Env) -> None:
    await scan_titles(env, [f"Backend Engineer {n}" for n in range(1, 13)])
    env.llm.add(
        answer(*[(f"j{n}", True, "fits") for n in range(1, 11)]),
        answer(("j1", True, "fits"), ("j2", True, "fits")),
    )

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert [c.prompt.user.count('"ref"') for c in env.llm.calls] == [10, 2]
    assert {r.decided_by for r in (await decisions(env)).values()} == {"ai"}


async def test_role_from_the_judge_is_stored_and_shown(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer (Python) - Pune")]))
    env.llm.add(
        {
            "decisions": [
                {"ref": "j1", "relevant": True, "reason": "Fits", "role": "Backend Engineer"}
            ]
        }
    )

    await go(env, await new_search(env, mode="rules_and_ai"))

    async with env.sessions() as session:
        row = (await session.scalars(select(JobRow))).one()
    assert row.role_short == "Backend Engineer"


async def test_no_role_from_the_judge_leaves_it_empty(env: Env) -> None:
    await scan_titles(env, TITLES[:1])
    env.llm.add(answer(("j1", True, "Fits")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    async with env.sessions() as session:
        row = (await session.scalars(select(JobRow))).one()
    assert row.role_short is None
