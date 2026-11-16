"""002i follow-up: a job already in the pipeline is not listed again by a later search.

The same posting can come back under another link (a board and a careers page, or a renamed link).
Exact keys merge it; when only the company, the city and a near-identical title match a job that is
already applied or inquired, the new row would give the person two rows with two statuses, so it is
left out with that reason and can be restored.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.search.application.ports import ScanOk
from hiretitan.search.infra.models import JobRow


async def mark(env: Env, title: str, state: str) -> None:
    async with env.sessions() as session:
        day = datetime(2026, 11, 5, tzinfo=UTC).date()
        marks = {"applied_on": day} if state == "applied" else {"inquired_on": day}
        await session.execute(
            update(JobRow).where(JobRow.title == title).values(state=state, **marks)
        )
        await session.commit()


async def rows(env: Env) -> list[JobRow]:
    async with env.sessions() as session:
        return list((await session.scalars(select(JobRow).order_by(JobRow.created_at))).all())


async def test_same_job_under_another_link_is_not_listed_again_when_in_pipeline(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env))
    await mark(env, "Backend Engineer", "inquired")

    # a later search finds it again, on another link
    env.career_ops.script(
        ref,
        ScanOk([posting("Backend Engineer", url="https://careers.example.com/acme/be-1")]),
    )
    await go(env, await new_search(env))

    found = await rows(env)
    assert len(found) == 2
    again = next(r for r in found if r.state != "inquired")
    assert again.state == "skipped"  # not a second row to apply to


async def test_a_different_role_at_the_same_company_is_still_listed(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env))
    await mark(env, "Backend Engineer", "applied")

    env.career_ops.script(ref, ScanOk([posting("Senior Backend Engineer")]))
    await go(env, await new_search(env))

    assert {r.title: r.state for r in await rows(env)} == {
        "Backend Engineer": "applied",
        "Senior Backend Engineer": "explore",
    }


async def test_a_near_copy_of_a_job_not_in_the_pipeline_is_still_listed(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env))  # stays in Explore

    env.career_ops.script(
        ref,
        ScanOk([posting("Backend Engineer", url="https://careers.example.com/acme/be-1")]),
    )
    await go(env, await new_search(env))

    assert [r.state for r in await rows(env)] == ["explore", "explore"]  # the person decides
