"""T032: how a search ends early and what it keeps (US1 AS8/AS9, FR-010a, FR-028, SC-006a)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.platform.llm.port import AiUnavailable, RetryableLlmError
from hiretitan.search.application.ports import ScanOk
from hiretitan.search.infra.models import JobRow, RelevanceDecisionRow, SearchRunRow
from hiretitan.search.infra.repos import SearchRunsRepo

MESSAGE = "You exceeded your current quota, please check your plan and billing details."


async def nine_companies(env: Env) -> None:
    for i in range(9):  # two batches: 8 + 1
        ref = await add_company(env, f"C{i}")
        env.career_ops.script(ref, ScanOk([posting("Backend Engineer", ref.board_id)]))


def all_yes(count: int) -> dict[str, Any]:
    return {
        "decisions": [
            {"ref": f"j{n}", "relevant": True, "reason": "fits"} for n in range(1, count + 1)
        ]
    }


async def latest(env: Env) -> SearchRunRow:
    async with env.sessions() as session:
        run = await SearchRunsRepo(session).latest()
    assert run is not None
    return run


async def count(env: Env, model: Any, *where: Any) -> int:
    async with env.sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def test_US1_AS8_out_of_credit_stops_keeps_batches_and_shows_message(env: Env) -> None:
    await nine_companies(env)
    env.llm.add(AiUnavailable("out_of_credit", MESSAGE))

    await go(env, await new_search(env, mode="rules_and_ai"))

    run = await latest(env)
    assert (run.outcome, run.stop_message) == ("out_of_credit", MESSAGE)
    assert (run.batches_done, run.next_index, run.added) == (1, 8, 8)  # the first batch is kept
    assert len(env.career_ops.scan_calls) == 1  # the second batch was never read
    assert (
        await count(
            env, RelevanceDecisionRow, RelevanceDecisionRow.decided_by == "rules_only_fallback"
        )
        == 8
    )
    events = [e for e, _ in env.published]
    assert events == ["search.batch_done", "search.finished"]
    assert env.published[-1][1]["outcome"] == "out_of_credit"
    assert env.published[-1][1]["stop_message"] == MESSAGE


async def test_SC006a_out_of_credit_call_is_not_retried(env: Env) -> None:
    await nine_companies(env)
    env.llm.add(AiUnavailable("out_of_credit", MESSAGE), AiUnavailable("out_of_credit", MESSAGE))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert len(env.llm.calls) == 1


async def test_US1_AS8_budget_reached_stops_and_next_search_continues(env: Env) -> None:
    await nine_companies(env)
    env.llm.add(AiUnavailable("budget_reached"))
    await go(env, await new_search(env, mode="rules_and_ai"))
    run = await latest(env)
    assert (run.outcome, run.next_index) == ("budget_reached", 8)

    unread = (await latest(env)).company_order[8]  # the company the stopped search never reached

    env.llm.add(all_yes(8), all_yes(1))
    await go(env, await new_search(env, mode="rules_and_ai"))

    second = env.career_ops.scan_calls[1]
    assert second[0].company_id == unread  # FR-010a: the leftover company is read first
    run = await latest(env)
    assert (run.outcome, run.next_index) == ("finished", 9)


async def test_US1_AS9_stop_after_current_batch(env: Env) -> None:
    await nine_companies(env)
    inner = env.deps.publish
    assert inner is not None

    async def stop_on_first_batch(event: str, data: dict[str, object]) -> None:
        await inner(event, data)
        if event == "search.batch_done":
            async with env.sessions() as session:
                await session.execute(update(SearchRunRow).values(stop_requested=True))
                await session.commit()

    env.deps.publish = stop_on_first_batch
    env.llm.add(all_yes(8))

    await go(env, await new_search(env, mode="rules_and_ai"))

    run = await latest(env)
    assert (run.outcome, run.batches_done, run.next_index) == ("stopped_by_user", 1, 8)
    assert len(env.career_ops.scan_calls) == 1
    assert await count(env, JobRow) == 8
    assert env.published[-1][0] == "search.finished"
    assert env.published[-1][1]["outcome"] == "stopped_by_user"


async def test_SC009_ai_down_still_processes_all_sources_by_rules(env: Env) -> None:
    await nine_companies(env)
    env.llm.add(RetryableLlmError("timeout"), RetryableLlmError("timeout"))

    await go(env, await new_search(env, mode="rules_and_ai"))

    run = await latest(env)
    assert (run.outcome, run.added, run.next_index) == ("finished", 9, 9)
    assert (
        await count(
            env, RelevanceDecisionRow, RelevanceDecisionRow.decided_by == "rules_only_fallback"
        )
        == 9
    )
