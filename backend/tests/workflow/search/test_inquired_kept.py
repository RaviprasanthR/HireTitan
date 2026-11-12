"""002d: a search leaves an inquired job alone (SC-006)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.search.application.ports import ScanOk
from hiretitan.search.infra.models import JobRow


async def test_SC006_search_again_keeps_inquired_jobs(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env, mode="rules_only"))
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow))).one()
        job.state = "inquired"
        job.inquired_on = date(2026, 11, 3)
        await session.commit()

    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env, mode="rules_only"))

    async with env.sessions() as session:
        jobs = list(await session.scalars(select(JobRow)))
    assert [(j.state, j.inquired_on) for j in jobs] == [("inquired", date(2026, 11, 3))]
