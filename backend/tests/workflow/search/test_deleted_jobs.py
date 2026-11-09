"""T035: a job the person deleted is not added again by a later search (FR-041)."""

from __future__ import annotations

from sqlalchemy import func, select
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.search.application.ports import ScanOk
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.repos import JobsRepo


async def test_FR041_deleted_job_not_readded_by_next_search(env: Env) -> None:
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env, mode="rules_only"))
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow))).one()
        await JobsRepo(session).set_state(job.id, "deleted")
        await session.commit()

    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))
    await go(env, await new_search(env, mode="rules_only"))

    async with env.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(JobRow)) == 1
        assert (await session.scalars(select(JobRow.state))).one() == "deleted"
