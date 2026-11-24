"""When a check starts on its own (T039): US5 AS1, FR-021.

The hourly tick starts a check once 24 hours have passed since the last one; Search now chains a
mail check after the company search; neither ever starts a check that could not run.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from tests.fakes.mail_env import make_run
from tests.workflow.mail.test_check import NOW, Env, set_rules, the_check

from hiretitan.mail.application.ports import CheckNotReadyError
from hiretitan.mail.infra.models import MailCheckRow
from hiretitan.mail.infra.repos import ConnectionRepo
from hiretitan.mail.workflow.schedule import ScheduleDeps, after_company_search, daily_tick
from hiretitan.mail_wiring import chain_mail_after_search
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.domain.rules import SearchRules
from hiretitan.search.infra.repos import SearchRunsRepo


def schedule(env: Env) -> ScheduleDeps:
    return ScheduleDeps(sessions=env.sessions, runs=env.runs, clock=env.clock)


async def last_check(env: Env, ago: timedelta | None) -> None:
    if ago is None:
        return
    async with env.sessions() as session:
        await ConnectionRepo(session).mark_check_started(NOW - ago)
        await session.commit()


async def checks(env: Env) -> list[MailCheckRow]:
    async with env.sessions() as session:
        return list((await session.scalars(select(MailCheckRow))).all())


async def test_US5_AS1_daily_tick_checks_after_24h(env: Env) -> None:
    await last_check(env, timedelta(hours=25))

    started = await daily_tick(schedule(env))

    assert started is not None
    assert len(env.queued) == 1  # handed to the worker
    (check,) = await checks(env)
    assert (check.trigger, check.search_run_id) == ("daily", started)


async def test_US5_AS1_daily_tick_does_nothing_before_24h(env: Env) -> None:
    await last_check(env, timedelta(hours=23, minutes=59))

    assert await daily_tick(schedule(env)) is None
    assert env.queued == []
    assert await checks(env) == []


async def test_FR021_tick_checks_soon_after_start_when_overdue(env: Env) -> None:
    # HireTitan was off for days: the check made when it starts is the same tick
    await last_check(env, timedelta(days=4))

    assert await daily_tick(schedule(env)) is not None


async def test_FR021_tick_checks_when_never_checked(env: Env) -> None:
    await last_check(env, None)

    assert await daily_tick(schedule(env)) is not None


async def test_FR021_tick_skips_when_search_running(env: Env) -> None:
    await last_check(env, timedelta(hours=30))
    async with env.sessions() as session:
        await make_run(session, mode="rules_only")  # a company search is running
        await session.commit()

    assert await daily_tick(schedule(env)) is None  # no error: the next hour tries again
    assert env.queued == []
    assert await checks(env) == []


async def test_FR021_tick_does_not_start_a_second_check(env: Env) -> None:
    await last_check(env, timedelta(hours=30))
    first = await daily_tick(schedule(env))

    assert first is not None
    assert await daily_tick(schedule(env)) is None  # the first is still queued or running
    assert len(env.queued) == 1


async def test_FR021_not_connected_never_checks(env: Env) -> None:
    async with env.sessions() as session:
        await ConnectionRepo(session).remove()
        await session.commit()

    assert await daily_tick(schedule(env)) is None
    assert await after_company_search(schedule(env)) is None
    assert env.queued == []


async def test_FR021_needs_reconnect_never_checks(env: Env) -> None:
    await last_check(env, timedelta(hours=30))
    async with env.sessions() as session:
        await ConnectionRepo(session).set_state("needs_reconnect", "Gmail access has ended.")
        await session.commit()

    assert await daily_tick(schedule(env)) is None
    assert env.queued == []


async def test_FR021_rules_not_approved_waits_quietly(env: Env) -> None:
    await last_check(env, timedelta(hours=30))
    async with env.sessions() as session:
        await session.execute(text("DELETE FROM app.search_rule_sets"))
        await session.commit()

    assert await daily_tick(schedule(env)) is None
    assert env.queued == []


async def test_FR021_search_now_queues_mail_check_when_connected(env: Env) -> None:
    await set_rules(env, SearchRules())
    await last_check(env, timedelta(hours=1))  # not due: Search now checks anyway

    started = await after_company_search(schedule(env))

    assert started is not None
    (check,) = await checks(env)
    assert check.trigger == "search_now"
    assert len(env.queued) == 1


async def _finished_company_search(env: Env, outcome: str) -> UUID:
    async with env.sessions() as session:
        search_run = await make_run(session, mode="rules_only")
        run = await SearchRunsRepo(session).get(search_run)
        assert run is not None
        workflow_id = run.workflow_run_id
        await RunsRepo(session).transition(workflow_id, RunStatus.running)
        await SearchRunsRepo(session).finish(
            search_run, outcome=outcome, finished_at=NOW, stop_message=None
        )
        await RunsRepo(session).transition(workflow_id, RunStatus.done)
        await session.commit()
        return workflow_id


async def _notify_done(env: Env, workflow_id: UUID, seen: list[object]) -> None:
    async def base(run: object) -> None:
        seen.append(run)

    notify = chain_mail_after_search(base, env.sessions, schedule(env))  # type: ignore[arg-type]
    async with env.sessions() as session:
        run = await RunsRepo(session).get(workflow_id)
    assert run is not None
    await notify(run)


async def test_FR021_a_finished_company_search_is_followed_by_a_mail_check(env: Env) -> None:
    workflow_id = await _finished_company_search(env, "finished")
    seen: list[object] = []

    await _notify_done(env, workflow_id, seen)

    assert len(seen) == 1  # the normal notice still goes out
    (check,) = await checks(env)
    assert check.trigger == "search_now"
    assert (await the_check(env, check.search_run_id)).trigger == "search_now"


@pytest.mark.parametrize(
    "outcome", ["stopped_by_user", "budget_reached", "out_of_credit", "failed"]
)
async def test_FR021_a_company_search_that_did_not_finish_is_not_followed_by_a_mail_check(
    env: Env, outcome: str
) -> None:
    workflow_id = await _finished_company_search(env, outcome)

    await _notify_done(env, workflow_id, [])

    assert await checks(env) == []
    assert env.queued == []


async def test_FR021_the_mail_checks_own_end_starts_nothing(env: Env) -> None:
    env.add("linkedin-01")
    run_id = await env.check()
    async with env.sessions() as session:
        run = await SearchRunsRepo(session).get(run_id)
        assert run is not None
        workflow = await RunsRepo(session).get(run.workflow_run_id)
    assert workflow is not None
    before = len(await checks(env))

    await _notify_done(env, workflow.id, [])

    assert len(await checks(env)) == before


async def test_FR021_a_mail_check_and_a_company_search_cannot_start_together(env: Env) -> None:
    import asyncio

    from hiretitan.search.application.search import SearchAlreadyRunningError
    from hiretitan.search.infra.repos import RuleSetsRepo
    from hiretitan.search.infra.search_store import SearchStore

    async def company_search() -> str:
        async with env.sessions() as session:
            rules = await RuleSetsRepo(session).approved()
            assert rules is not None
            try:
                await SearchStore(session).create_run(rules.id, "rules_only", NOW)
            except SearchAlreadyRunningError:
                return "refused"
            await session.commit()
            return "started"

    async def mail_check() -> str:
        try:
            await env.runs.start(trigger="button", now=NOW)
        except CheckNotReadyError:
            return "refused"
        return "started"

    for _ in range(5):  # a few rounds: the race is tiny, the rule must hold every time
        results = await asyncio.gather(company_search(), mail_check())
        assert sorted(results) == ["refused", "started"], results
        async with env.sessions() as session:
            await session.execute(text("DELETE FROM app.search_runs"))
            await session.execute(text("DELETE FROM app.workflow_runs"))
            await session.commit()


async def ended_last_check(env: Env, ended: str, ago: timedelta) -> None:
    """A check that ran ``ago`` and ended as ``ended``."""
    env.add("linkedin-01")
    await env.check()
    async with env.sessions() as session:
        await session.execute(text("UPDATE app.mail_checks SET ended = :e"), {"e": ended})
        await ConnectionRepo(session).mark_check_started(NOW - ago)
        await session.commit()
    env.queued.clear()


@pytest.mark.parametrize("ended", ["gmail_unavailable", "failed"])
async def test_FR021_a_failed_check_is_tried_again_an_hour_later(env: Env, ended: str) -> None:
    await ended_last_check(env, ended, timedelta(hours=1, minutes=5))

    assert await daily_tick(schedule(env)) is not None


async def test_FR021_a_failed_check_is_not_retried_within_the_hour(env: Env) -> None:
    await ended_last_check(env, "gmail_unavailable", timedelta(minutes=30))

    assert await daily_tick(schedule(env)) is None


@pytest.mark.parametrize("ended", ["finished", "stopped"])
async def test_FR021_a_check_that_ended_normally_waits_the_full_day(env: Env, ended: str) -> None:
    await ended_last_check(env, ended, timedelta(hours=2))

    assert await daily_tick(schedule(env)) is None
