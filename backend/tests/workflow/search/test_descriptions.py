"""002i T013: a job's description is read after the free rules and before the AI check (FR-029).

Reading is for jobs the rules kept, in searches with the AI check on. The text is cleaned and
screened like any job text, refreshes the skills and years found, and a failed read is told to the
model and noted in the reason when the job is kept (FR-034).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlalchemy import select
from tests.fakes.descriptions import FakeDescriptions
from tests.fakes.search_env import RULES, Env, add_company, go, new_search, posting

from hiretitan.search.application.ports import DescribeRequest, ScanOk
from hiretitan.search.domain.rules import RuleItem
from hiretitan.search.infra.models import JobRow, RelevanceDecisionRow, SearchRunRow
from hiretitan.search.infra.repos import SearchRunsRepo

RULES_WITH_STACK = replace(
    RULES, stack_keywords=(RuleItem("Python", "user"), RuleItem("FastAPI", "user"))
)


def answer(*pairs: tuple[str, bool, str]) -> dict[str, Any]:
    return {"decisions": [{"ref": r, "relevant": ok, "reason": why} for r, ok, why in pairs]}


def link(title: str) -> str:
    return f"https://jobs.example.com/acme/{title.replace(' ', '-')}"


def descriptions_of(env: Env) -> FakeDescriptions:
    port = env.deps.descriptions
    assert isinstance(port, FakeDescriptions)
    return port


async def scan(env: Env, *titles: str, description: str = "") -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting(t, description=description) for t in titles]))


async def one(env: Env, title: str) -> JobRow:
    async with env.sessions() as session:
        return (await session.scalars(select(JobRow).where(JobRow.title == title))).one()


async def reason_of(env: Env, title: str) -> str:
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow).where(JobRow.title == title))).one()
        row = await session.scalar(
            select(RelevanceDecisionRow).where(
                RelevanceDecisionRow.job_id == job.id, RelevanceDecisionRow.is_current
            )
        )
    assert row is not None
    return row.reason


async def test_FR029_descriptions_read_for_kept_jobs_only(env: Env) -> None:
    await scan(env, "Backend Engineer", "Sales Executive")  # the rules keep only the first
    env.deps.descriptions = FakeDescriptions({link("Backend Engineer"): "Build Python APIs."})
    env.llm.add(answer(("j1", True, "Python backend role")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert descriptions_of(env).urls() == [link("Backend Engineer")]
    job = await one(env, "Backend Engineer")
    assert job.description == "Build Python APIs."  # stored with the job
    assert (await one(env, "Sales Executive")).description == ""  # skipped, never read


async def test_FR029_rules_only_reads_nothing(env: Env) -> None:
    await scan(env, "Backend Engineer")
    env.deps.descriptions = FakeDescriptions({link("Backend Engineer"): "Build Python APIs."})

    await go(env, await new_search(env, mode="rules_only"))

    assert descriptions_of(env).calls == []
    assert (await one(env, "Backend Engineer")).description == ""


async def test_FR029_a_description_that_came_with_the_listing_is_not_read_again(env: Env) -> None:
    await scan(env, "Backend Engineer", description="Already here.")
    env.deps.descriptions = FakeDescriptions()
    env.llm.add(answer(("j1", True, "Fits")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert descriptions_of(env).calls == []
    assert (await one(env, "Backend Engineer")).description == "Already here."


async def test_FR029_description_refreshes_skills_and_years(env: Env) -> None:
    await scan(env, "Backend Engineer")
    env.deps.descriptions = FakeDescriptions(
        {link("Backend Engineer"): "We use Python and FastAPI. 5+ years of experience."}
    )
    env.llm.add(answer(("j1", True, "Fits")))

    await go(env, await new_search(env, rules=RULES_WITH_STACK, mode="rules_and_ai"))

    job = await one(env, "Backend Engineer")
    assert set(job.skills_found) == {"Python", "FastAPI"}
    assert job.years_found is not None
    assert int(job.years_found) == 5


async def test_FR034_unreadable_description_is_told_to_the_ai(env: Env) -> None:
    await scan(env, "Backend Engineer")
    env.deps.descriptions = FakeDescriptions()  # no text for any link: every read fails
    env.llm.add(answer(("j1", True, "Python backend role")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    sent = env.llm.calls[-1].prompt.user
    assert '"description_status": "unreadable"' in sent


async def test_FR034_kept_without_description_says_so_in_the_reason(env: Env) -> None:
    await scan(env, "Backend Engineer", "Backend Engineer II")
    env.deps.descriptions = FakeDescriptions({link("Backend Engineer II"): "Python APIs."})
    env.llm.add(answer(("j1", True, "Python backend role"), ("j2", True, "Python backend role")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert await reason_of(env, "Backend Engineer") == (
        "Python backend role Description could not be read."
    )
    assert await reason_of(env, "Backend Engineer II") == "Python backend role"


async def test_FR029_a_job_left_out_by_the_ai_keeps_the_models_reason(env: Env) -> None:
    await scan(env, "Backend Engineer")
    env.deps.descriptions = FakeDescriptions()
    env.llm.add(answer(("j1", False, "Mostly frontend work")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert await reason_of(env, "Backend Engineer") == "Mostly frontend work"


async def test_FR029_stop_during_reads_keeps_finished_jobs(env: Env) -> None:
    titles = [f"Backend Engineer {n}" for n in ("A", "B", "C", "D")]
    await scan(env, *titles)
    descriptions = FakeDescriptions({link(t): "Python APIs." for t in titles})

    async def press_stop(_: DescribeRequest) -> None:
        async with env.sessions() as session:
            run = await SearchRunsRepo(session).latest()
            assert run is not None
            await SearchRunsRepo(session).request_stop(run.id)
            await session.commit()

    descriptions.on_read = press_stop
    env.deps.descriptions = descriptions
    env.llm.add(answer(*[(f"j{n}", True, "Fits") for n in range(1, 5)]))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert len(descriptions.calls) == 1  # the stop was seen before the next read
    assert not env.llm.calls  # and no AI call is made after Stop (FR-010)
    async with env.sessions() as session:
        stored = (await session.scalars(select(JobRow))).all()
        run = (await session.scalars(select(SearchRunRow))).one()
    assert len(stored) == 4  # every job found is kept
    assert run.outcome == "stopped_by_user"


async def test_FR029_a_reader_that_crashes_is_an_unreadable_description(env: Env) -> None:
    await scan(env, "Backend Engineer")

    async def boom(_: DescribeRequest) -> None:
        raise RuntimeError("the reader fell over")

    descriptions = FakeDescriptions({link("Backend Engineer"): "Python APIs."})
    descriptions.on_read = boom
    env.deps.descriptions = descriptions
    env.llm.add(answer(("j1", True, "Python backend role")))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert (await reason_of(env, "Backend Engineer")).endswith("Description could not be read.")
