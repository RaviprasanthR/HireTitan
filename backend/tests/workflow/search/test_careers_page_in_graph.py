"""T054: companies read through their careers page inside the W3 graph (US3-AS3, FR-011,
FR-013, research R3)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select
from tests.fakes.pages import FakePages
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.search.application.ports import PageFetch, ScanOk
from hiretitan.search.infra.models import (
    CompanyRow,
    JobRow,
    JobSourceRow,
    SearchRunCompanyRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import CompaniesRepo

EXTRACT = "extract_jobs_from_page"
JUDGE = "judge_relevance"

JSON_LD = """<html><head><script type="application/ld+json">
{"@type": "JobPosting", "title": "Backend Engineer", "url": "https://one.example.com/jobs/be-1",
 "jobLocation": {"address": {"addressLocality": "Pune", "addressCountry": "IN"}}}
</script></head><body><h1>Careers</h1></body></html>"""

LINKS = """<html><body><h1>Join us</h1><p>We are a small team that likes simple, well-made things,
and we hire people who care about the details of their work, week after week, in a calm place.</p>
<ul><li><a href="/careers/backend-engineer-ii">Backend Engineer II</a></li></ul></body></html>"""

TABLE = """<html><body><h1>Current openings</h1><p>We are growing, and these are the roles we are
hiring for this quarter. Each one is described on its own page, which you reach with the Apply
button on the right of the row, and we answer every application within two weeks, always.</p>
<table><tr><td>Backend Engineer</td><td>Pune</td><td><a href="/apply?ref=1">Apply</a></td></tr>
</table></body></html>"""

SHELL = (
    '<html><head><script src="/app.js"></script></head><body><div id="root"></div></body></html>'
)


@dataclass
class Careers:
    id: object
    url: str


@pytest.fixture
def pages(env: Env) -> FakePages:
    fake = FakePages()
    env.deps.pages = fake
    env.deps.page_ai = True
    return fake


async def add_careers(env: Env, name: str, url: str, **fields: object) -> Careers:
    async with env.sessions() as session:
        row = await CompaniesRepo(session).add(
            name=name, origin="user", resolution="careers_page", careers_url=url, **fields
        )
        await session.commit()
        return Careers(row.id, url)


async def results(env: Env) -> dict[str, str]:
    async with env.sessions() as session:
        rows = await session.execute(
            select(CompanyRow.name, SearchRunCompanyRow.result).join(
                CompanyRow, CompanyRow.id == SearchRunCompanyRow.company_id
            )
        )
        return {name: result for name, result in rows}


async def run_row(env: Env) -> SearchRunRow:
    async with env.sessions() as session:
        return (await session.scalars(select(SearchRunRow))).one()


def tasks(env: Env) -> list[str]:
    return [call.task for call in env.llm.calls]


async def test_R3_json_ld_and_link_pages_are_read_without_the_ai(
    env: Env, pages: FakePages
) -> None:
    await add_careers(env, "One", "https://one.example.com/careers")
    await add_careers(env, "Two", "https://two.example.com/careers")
    pages.html("https://one.example.com/careers", JSON_LD)
    pages.html("https://two.example.com/careers", LINKS)
    env.llm.add(
        {
            "decisions": [
                {"ref": "j1", "relevant": True, "reason": "A"},
                {"ref": "j2", "relevant": True, "reason": "B"},
            ]
        },
        task=JUDGE,
    )

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert tasks(env) == [JUDGE]  # no AI call to read either page
    assert await results(env) == {"One": "ok", "Two": "ok"}
    async with env.sessions() as session:
        jobs = {j.title: j for j in await session.scalars(select(JobRow))}
        assert set(jobs) == {"Backend Engineer", "Backend Engineer II"}
        assert all(j.ats_vendor is None and j.state == "explore" for j in jobs.values())
        assert jobs["Backend Engineer"].city == "Pune"
        kinds = {s.kind for s in await session.scalars(select(JobSourceRow))}
        assert kinds == {"careers_page"}


async def test_R3_ai_fallback_only_when_no_structured_data(env: Env, pages: FakePages) -> None:
    await add_careers(env, "Tabular", "https://t.example.com/careers")
    pages.html("https://t.example.com/careers", TABLE)
    env.llm.add(
        {
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "url": "https://t.example.com/apply?ref=1",
                    "location": "Pune",
                }
            ]
        },
        task=EXTRACT,
    )
    env.llm.add(
        {"decisions": [{"ref": "j1", "relevant": True, "reason": "Python backend role"}]},
        task=JUDGE,
    )

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert tasks(env) == [EXTRACT, JUDGE]
    assert await results(env) == {"Tabular": "ok"}
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow))).one()
        assert (job.title, job.location_text, job.state) == ("Backend Engineer", "Pune", "explore")
        source = (await session.scalars(select(JobSourceRow))).one()
        assert (source.kind, source.url) == ("careers_page", "https://t.example.com/apply?ref=1")


async def test_the_ai_may_only_return_links_the_page_has(env: Env, pages: FakePages) -> None:
    await add_careers(env, "Tabular", "https://t.example.com/careers")
    pages.html("https://t.example.com/careers", TABLE)
    made_up = {"jobs": [{"title": "Backend Engineer", "url": "https://t.example.com/apply?ref=99"}]}
    env.llm.add(made_up, made_up, task=EXTRACT)  # the answer and its one repair

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert await results(env) == {"Tabular": "unreadable"}  # an answer we cannot use
    async with env.sessions() as session:
        assert (await session.scalars(select(JobRow))).all() == []


async def test_a_rules_only_search_never_asks_the_ai_to_read_a_page(
    env: Env, pages: FakePages
) -> None:
    await add_careers(env, "Tabular", "https://t.example.com/careers")
    pages.html("https://t.example.com/careers", TABLE)

    await go(env, await new_search(env, mode="rules_only"))

    assert env.llm.calls == []
    assert await results(env) == {"Tabular": "no_jobs"}


async def test_the_ai_page_step_stays_off_until_it_is_switched_on(
    env: Env, pages: FakePages
) -> None:
    env.deps.page_ai = False
    await add_careers(env, "Tabular", "https://t.example.com/careers")
    pages.html("https://t.example.com/careers", TABLE)

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert env.llm.calls == []
    assert await results(env) == {"Tabular": "no_jobs"}


async def test_US3_AS3_unreadable_company_goes_to_check_manually(
    env: Env, pages: FakePages
) -> None:
    await add_careers(env, "Shell", "https://s.example.com/careers")
    pages.html("https://s.example.com/careers", SHELL)
    ref = await add_company(env, "Acme")
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer")]))

    await go(env, await new_search(env))

    assert (await run_row(env)).outcome == "finished"
    assert await results(env) == {"Shell": "unreadable", "Acme": "ok"}
    async with env.sessions() as session:
        listed = [c.name for c in await CompaniesRepo(session).list_check_manually()]
        assert listed == ["Shell"]
        shell = (await session.scalars(select(CompanyRow).where(CompanyRow.name == "Shell"))).one()
        assert shell.last_check_result == "unreadable"
        assert shell.last_checked_at is not None
        assert shell.last_check_error
    assert [j for j in await jobs(env)] == ["Backend Engineer"]  # the board company still worked


async def test_FR013_blocked_company_never_fetched_and_listed(env: Env, pages: FakePages) -> None:
    await add_careers(env, "Closed", "https://c.example.com/careers")
    pages.script(
        "https://c.example.com/careers",
        PageFetch("blocked", error="The site does not allow automatic reading of this page."),
    )

    await go(env, await new_search(env))

    assert await results(env) == {"Closed": "blocked"}
    async with env.sessions() as session:
        assert [c.name for c in await CompaniesRepo(session).list_check_manually()] == ["Closed"]
        closed = (await session.scalars(select(CompanyRow))).one()
        assert "does not allow" in (closed.last_check_error or "")
    assert env.llm.calls == []


async def test_FR011_careers_failure_does_not_stop_search(env: Env, pages: FakePages) -> None:
    await add_careers(env, "Down", "https://d.example.com/careers")  # nothing scripted: fails
    await add_careers(env, "One", "https://one.example.com/careers")
    pages.html("https://one.example.com/careers", JSON_LD)

    await go(env, await new_search(env))

    assert (await run_row(env)).outcome == "finished"
    assert await results(env) == {"Down": "failed", "One": "ok"}
    assert await jobs(env) == ["Backend Engineer"]


async def test_out_of_credit_while_reading_a_page_stops_the_search(
    env: Env, pages: FakePages
) -> None:
    await add_careers(env, "Tabular", "https://t.example.com/careers")
    pages.html("https://t.example.com/careers", TABLE)
    env.llm.add(AiUnavailable("out_of_credit", "No credit left."), task=EXTRACT)

    await go(env, await new_search(env, mode="rules_and_ai"))

    run = await run_row(env)
    assert (run.outcome, run.stop_message) == ("out_of_credit", "No credit left.")
    assert await results(env) == {"Tabular": "failed"}  # read again by the next search


async def test_a_job_found_again_on_a_careers_page_is_not_added_twice(
    env: Env, pages: FakePages
) -> None:
    await add_careers(env, "One", "https://one.example.com/careers")
    pages.html("https://one.example.com/careers", JSON_LD)
    await go(env, await new_search(env))

    await go(env, await new_search(env))

    assert await jobs(env) == ["Backend Engineer"]
    async with env.sessions() as session:
        assert len((await session.scalars(select(JobSourceRow))).all()) == 1


async def test_a_hidden_careers_company_is_not_read(env: Env, pages: FakePages) -> None:
    await add_careers(env, "One", "https://one.example.com/careers", hidden=True)
    pages.html("https://one.example.com/careers", JSON_LD)

    await go(env, await new_search(env))

    assert pages.fetched == []
    assert await jobs(env) == []


async def test_without_a_page_reader_a_careers_company_is_unreadable(env: Env) -> None:
    await add_careers(env, "One", "https://one.example.com/careers")

    await go(env, await new_search(env))

    assert (await run_row(env)).outcome == "finished"
    assert await results(env) == {"One": "unreadable"}


async def jobs(env: Env) -> list[str]:
    async with env.sessions() as session:
        return sorted(j.title for j in await session.scalars(select(JobRow)))
