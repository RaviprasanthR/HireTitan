"""T030: the W3 graph without the AI step (US1, FR-010a, FR-011, FR-026)."""

from __future__ import annotations

from sqlalchemy import func, select, update
from tests.fakes.career_ops import FakeCareerOps  # noqa: F401
from tests.fakes.search_env import (
    NOW,
    Env,
    add_company,
    complete,
    go,
    new_search,
    posting,
    titles,
)

from hiretitan.search.application.ports import ScanError, ScanOk
from hiretitan.search.infra.models import (
    JobRow,
    RelevanceDecisionRow,
    SearchRunCompanyRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, SearchRunsRepo


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
