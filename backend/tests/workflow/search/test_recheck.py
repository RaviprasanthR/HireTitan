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
