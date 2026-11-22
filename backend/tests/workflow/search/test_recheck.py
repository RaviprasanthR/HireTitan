"""T035: re-judging one job that was shown as "not checked by AI" (FR-028)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from tests.fakes.descriptions import FakeDescriptions
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.application.ports import ScanOk
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.repos import DecisionsRepo
from hiretitan.search.workflow.recheck import RECHECK_WORKFLOW, run_recheck


async def unchecked_job(env: Env) -> UUID:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env, mode="rules_only"))  # no AI: "not checked by AI"
    async with env.sessions() as session:
        return (await session.scalars(select(JobRow))).one().id


async def recheck(env: Env, job_id: UUID) -> None:
    async with env.sessions() as session:
        run = await RunsRepo(session).create(RECHECK_WORKFLOW, subject_id=job_id)
        await session.commit()
    await run_recheck(env.deps, run.id, job_id)


async def state_and_decision(env: Env, job_id: UUID) -> tuple[str, str, str]:
    async with env.sessions() as session:
        job = await session.get(JobRow, job_id)
        decision = await DecisionsRepo(session).current(job_id)
    assert job is not None
    assert decision is not None
    return job.state, decision.decided_by, decision.outcome


async def test_recheck_keeps_a_relevant_job_with_the_ai_reason(env: Env) -> None:
    job_id = await unchecked_job(env)
    env.llm.add({"decisions": [{"ref": "j1", "relevant": True, "reason": "Fits"}]})

    await recheck(env, job_id)

    assert await state_and_decision(env, job_id) == ("explore", "ai", "shown")


async def test_recheck_moves_an_irrelevant_job_to_skipped(env: Env) -> None:
    job_id = await unchecked_job(env)
    env.llm.add({"decisions": [{"ref": "j1", "relevant": False, "reason": "Not backend"}]})

    await recheck(env, job_id)

    assert await state_and_decision(env, job_id) == ("skipped", "ai", "skipped")


async def test_recheck_pauses_when_the_ai_is_out_of_credit(env: Env) -> None:
    job_id = await unchecked_job(env)
    env.llm.add(AiUnavailable("out_of_credit", "quota"))

    with pytest.raises(AiUnavailable):
        await recheck(env, job_id)

    assert await state_and_decision(env, job_id) == ("explore", "rules_only_fallback", "shown")


async def test_recheck_leaves_the_job_when_the_answer_is_unusable(env: Env) -> None:
    job_id = await unchecked_job(env)
    env.llm.add({"decisions": []}, {"decisions": []})

    await recheck(env, job_id)

    assert await state_and_decision(env, job_id) == ("explore", "rules_only_fallback", "shown")


async def test_recheck_reads_description_first(env: Env) -> None:
    """002i FR-029: a job found without text gets it read before the AI is asked again."""
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer", description="")]))
    await go(env, await new_search(env, mode="rules_only"))
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow))).one()
        job_id, url = job.id, job.canonical_url
    assert url
    env.deps.descriptions = FakeDescriptions({url: "Build Python APIs for payments."})
    env.llm.add({"decisions": [{"ref": "j1", "relevant": True, "reason": "Fits"}]})

    await recheck(env, job_id)

    async with env.sessions() as session:
        stored = await session.get(JobRow, job_id)
    assert stored is not None
    assert stored.description == "Build Python APIs for payments."  # kept on the job
    sent = env.llm.calls[-1].prompt.user
    assert '"description_status": "read"' in sent
    assert "Build Python APIs for payments." in sent
    assert await state_and_decision(env, job_id) == ("explore", "ai", "shown")


async def test_recheck_without_a_reader_is_unchanged(env: Env) -> None:
    job_id = await unchecked_job(env)
    env.llm.add({"decisions": [{"ref": "j1", "relevant": True, "reason": "Fits"}]})

    await recheck(env, job_id)

    assert await state_and_decision(env, job_id) == ("explore", "ai", "shown")


async def _alert_job(env: Env, *, also_on_a_board: bool) -> tuple[UUID, str]:
    from datetime import UTC, datetime

    from hiretitan.search.infra.repos import JobsRepo

    url = "https://jobs.example.invalid/view/12345"
    now = datetime(2026, 11, 18, 9, tzinfo=UTC)
    async with env.sessions() as session:
        jobs = JobsRepo(session)
        job = await jobs.add(
            company_id=None,
            company_name="Acme",
            title="Backend Engineer",
            canonical_url=url,
            first_seen_at=now,
            last_seen_at=now,
            description="",
            state="explore",
        )
        await jobs.add_source(job.id, kind="email_alert", url=url, seen_at=now, search_run_id=None)
        if also_on_a_board:
            await jobs.add_source(
                job.id, kind="company_board", url=url, seen_at=now, search_run_id=None
            )
        await DecisionsRepo(session).record(
            job.id,
            outcome="shown",
            decided_by="rules_only_fallback",
            reason="Not checked by AI: no description yet",
        )
        await session.commit()
        return job.id, url


async def test_FR015_a_job_known_only_from_an_email_alert_is_never_fetched(env: Env) -> None:
    """HireTitan never fetches the posting page of an alert site: the person opens the link and
    pastes the description. "Check again" judges what is known and reads nothing."""
    job_id, url = await _alert_job(env, also_on_a_board=False)
    reader = FakeDescriptions({url: "Build Python APIs for payments."})
    env.deps.descriptions = reader
    env.llm.add({"decisions": [{"ref": "j1", "relevant": True, "reason": "Fits"}]})

    await recheck(env, job_id)

    assert reader.calls == []  # nothing was fetched
    async with env.sessions() as session:
        stored = await session.get(JobRow, job_id)
    assert stored is not None
    assert stored.description == ""
    assert await state_and_decision(env, job_id) == ("explore", "ai", "shown")


async def test_FR015_a_job_that_is_also_on_a_company_board_may_be_read(env: Env) -> None:
    job_id, url = await _alert_job(env, also_on_a_board=True)
    reader = FakeDescriptions({url: "Build Python APIs for payments."})
    env.deps.descriptions = reader
    env.llm.add({"decisions": [{"ref": "j1", "relevant": True, "reason": "Fits"}]})

    await recheck(env, job_id)

    assert reader.urls() == [url]
