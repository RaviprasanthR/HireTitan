"""T011: the search repositories (data-model.md; SC-010 paging, FR-009, FR-021)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.domain.vendors import ENABLED_VENDORS
from hiretitan.search.infra.repos import (
    CompaniesRepo,
    DecisionsRepo,
    DuplicatesRepo,
    JobFilters,
    JobsRepo,
    RuleSetsRepo,
    SearchRunsRepo,
)

T0 = datetime(2026, 11, 1, tzinfo=UTC)


async def add_company(
    session: AsyncSession,
    name: str = "Acme",
    *,
    vendor: str | None = None,
    resolution: str = "unresolved",
    **flags: object,
) -> UUID:
    repo = CompaniesRepo(session)
    company = await repo.add(
        name=name,
        origin="user",
        resolution=resolution,
        ats_vendor=vendor,
        board_id="board" if vendor else None,
    )
    for field, value in flags.items():
        await repo.set_fields(company.id, **{field: value})
    return company.id


async def add_job(
    session: AsyncSession,
    title: str = "Backend Engineer",
    *,
    company: str = "Acme",
    state: str = "explore",
    posted_days_ago: int | None = 1,
    **extra: object,
) -> UUID:
    job = await JobsRepo(session).add(
        company_name=company,
        title=title,
        description="text",
        state=state,
        posted_at=None if posted_days_ago is None else T0 - timedelta(days=posted_days_ago),
        first_seen_at=T0,
        last_seen_at=T0,
        applied_on=T0.date() if state == "applied" else None,
        **extra,
    )
    return job.id


# --- companies -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vendor", "resolution", "hidden", "deleted", "readable"),
    [
        ("greenhouse", "verified", False, False, True),
        ("workday", "user_confirmed", False, False, True),
        (None, "careers_page", False, False, True),
        ("keka", "verified", False, False, False),  # not an enabled provider
        (None, "unresolved", False, False, False),
        (None, "check_manually", False, False, False),
        ("greenhouse", "verified", True, False, False),  # hidden
        ("greenhouse", "verified", False, True, False),  # deleted
        (None, "careers_page", True, False, False),
    ],
)
async def test_company_readable_rule(
    db_session: AsyncSession,
    vendor: str | None,
    resolution: str,
    hidden: bool,
    deleted: bool,
    readable: bool,
) -> None:
    flags: dict[str, object] = {"hidden": hidden}
    if deleted:
        flags["deleted_at"] = T0
    company_id = await add_company(db_session, vendor=vendor, resolution=resolution, **flags)

    ids = {c.id for c in await CompaniesRepo(db_session).list_readable()}

    assert (company_id in ids) is readable


def test_enabled_vendors_match_research_r2() -> None:
    assert {
        "greenhouse",
        "lever",
        "ashby",
        "workday",
        "smartrecruiters",
        "recruitee",
        "zoho_recruit",
        "amazon",
    } == ENABLED_VENDORS


async def test_check_manually_list_membership(db_session: AsyncSession) -> None:
    manual = await add_company(db_session, "Manual", resolution="check_manually")
    blocked = await add_company(
        db_session, "Blocked", resolution="careers_page", last_check_result="blocked"
    )
    unreadable = await add_company(
        db_session, "Unreadable", resolution="careers_page", last_check_result="unreadable"
    )
    fine = await add_company(db_session, "Fine", vendor="lever", resolution="verified")
    failed = await add_company(
        db_session, "Failed", vendor="lever", resolution="verified", last_check_result="failed"
    )
    gone = await add_company(db_session, "Gone", resolution="check_manually", deleted_at=T0)

    ids = {c.id for c in await CompaniesRepo(db_session).list_check_manually()}

    assert ids >= {manual, blocked, unreadable}
    assert not ids & {fine, failed, gone}


async def test_company_key_lookup(db_session: AsyncSession) -> None:
    repo = CompaniesRepo(db_session)
    added = await repo.add(name="Acme", origin="built_in", resolution="verified", key="acme")
    assert (await repo.get_by_key("acme")).id == added.id  # type: ignore[union-attr]
    assert await repo.get_by_key("nobody") is None


# --- jobs: paging ----------------------------------------------------------------------------


async def test_SC010_keyset_paging_is_stable_while_rows_are_added(db_session: AsyncSession) -> None:
    repo = JobsRepo(db_session)
    original = [await add_job(db_session, f"Job {i}", posted_days_ago=i + 1) for i in range(60)]

    first = await repo.page(JobFilters(state="explore"), limit=25)
    assert len(first.items) == 25
    assert first.next_cursor is not None

    # a newer job and an older job arrive between page 1 and page 2
    await add_job(db_session, "Brand new", posted_days_ago=0)
    await add_job(db_session, "Ancient", posted_days_ago=400)

    second = await repo.page(JobFilters(state="explore"), limit=25, cursor=first.next_cursor)
    third = await repo.page(JobFilters(state="explore"), limit=25, cursor=second.next_cursor)

    seen = [j.id for j in [*first.items, *second.items, *third.items]]
    assert len(seen) == len(set(seen))  # nothing twice
    assert set(original) <= set(seen)  # nothing missed
    assert "Brand new" not in [j.title for j in second.items + third.items]  # newer = page 1 only
    assert third.next_cursor is None


async def test_page_size_defaults_to_25_and_caps_at_100(db_session: AsyncSession) -> None:
    repo = JobsRepo(db_session)
    for i in range(110):
        await add_job(db_session, f"Job {i}", posted_days_ago=i)
    assert len((await repo.page(JobFilters(state="explore"))).items) == 25
    assert len((await repo.page(JobFilters(state="explore"), limit=500)).items) == 100


async def test_page_orders_newest_first_with_unposted_by_first_seen(
    db_session: AsyncSession,
) -> None:
    repo = JobsRepo(db_session)
    old = await add_job(db_session, "Old", posted_days_ago=10)
    unposted = await add_job(db_session, "Unposted", posted_days_ago=None)  # sorts by first_seen
    recent = await add_job(db_session, "Recent", posted_days_ago=1)

    ids = [j.id for j in (await repo.page(JobFilters(state="explore"))).items]

    assert ids == [unposted, recent, old]


async def test_page_filters(db_session: AsyncSession) -> None:
    repo = JobsRepo(db_session)
    acme = await add_company(db_session, "Acme")
    remote = await add_job(
        db_session, "Remote one", company_id=acme, work_mode="remote", city="Pune"
    )
    onsite = await add_job(db_session, "Onsite one", work_mode="onsite", city="Chennai")
    skipped = await add_job(db_session, "Skipped one", state="skipped")
    await repo.add_source(onsite, kind="company_board", url="https://a.example/1", seen_at=T0)
    await repo.add_source(remote, kind="careers_page", url="https://a.example/2", seen_at=T0)

    async def ids(**kw: object) -> set[UUID]:
        page = await repo.page(JobFilters(**kw))  # type: ignore[arg-type]
        return {j.id for j in page.items}

    assert await ids(state="explore") == {remote, onsite}
    assert await ids(state="skipped") == {skipped}
    assert await ids(state="explore", company_id=acme) == {remote}
    assert await ids(state="explore", work_mode="onsite") == {onsite}
    assert await ids(state="explore", city="pune") == {remote}  # case-insensitive
    assert await ids(state="explore", source_kind="careers_page") == {remote}


async def test_page_sorted_by_company(db_session: AsyncSession) -> None:
    repo = JobsRepo(db_session)
    b = await add_job(db_session, "B role", company="beta")
    a = await add_job(db_session, "A role", company="Alpha")
    c = await add_job(db_session, "C role", company="Gamma")

    first = await repo.page(JobFilters(state="explore", sort="company"), limit=2)
    second = await repo.page(
        JobFilters(state="explore", sort="company"), limit=2, cursor=first.next_cursor
    )

    assert [j.id for j in first.items] == [a, b]
    assert [j.id for j in second.items] == [c]


# --- decisions -------------------------------------------------------------------------------


async def test_current_decision_is_unique(db_session: AsyncSession) -> None:
    job_id = await add_job(db_session)
    repo = DecisionsRepo(db_session)

    first = await repo.record(
        job_id, outcome="skipped", decided_by="rule", reason="title does not match"
    )
    second = await repo.record(
        job_id, outcome="shown", decided_by="person", reason="restored by you"
    )

    current = await repo.current(job_id)
    assert current is not None
    assert current.id == second.id
    history = await repo.history(job_id)
    assert [d.id for d in history] == [first.id, second.id]  # oldest first, both kept
    assert [d.is_current for d in history] == [False, True]


async def test_database_still_refuses_two_current_decisions(db_session: AsyncSession) -> None:
    job_id = await add_job(db_session)
    repo = DecisionsRepo(db_session)
    await repo.record(job_id, outcome="shown", decided_by="ai", reason="fits")
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.record(
                job_id, outcome="shown", decided_by="ai", reason="again", supersede=False
            )


# --- rule sets -------------------------------------------------------------------------------


async def test_rule_set_lifecycle(db_session: AsyncSession) -> None:
    repo = RuleSetsRepo(db_session)
    assert await repo.approved() is None

    first = await repo.propose({"title_words": ["a"]}, {"profile_version_id": "p1"})
    assert first.version == 1
    approved = await repo.approve(first.id)
    assert approved.status == "approved"
    assert (await repo.approved()).id == first.id  # type: ignore[union-attr]

    second = await repo.propose({"title_words": ["b"]}, {"profile_version_id": "p2"})
    assert second.version == 2
    assert (await repo.approved()).id == first.id  # type: ignore[union-attr]  # US2-AS4: unchanged
    assert (await repo.proposed()).id == second.id  # type: ignore[union-attr]

    await repo.approve(second.id)
    assert (await repo.approved()).id == second.id  # type: ignore[union-attr]
    assert await repo.proposed() is None
    assert (await repo.get(first.id)).status == "superseded"  # type: ignore[union-attr]


async def test_a_new_proposal_replaces_the_open_one(db_session: AsyncSession) -> None:
    repo = RuleSetsRepo(db_session)
    await repo.propose({"v": 1}, {})
    newer = await repo.propose({"v": 2}, {})
    assert (await repo.proposed()).id == newer.id  # type: ignore[union-attr]


async def test_discard_proposal(db_session: AsyncSession) -> None:
    repo = RuleSetsRepo(db_session)
    await repo.propose({"v": 1}, {})
    await repo.discard_proposed()
    assert await repo.proposed() is None


# --- search runs -----------------------------------------------------------------------------


async def make_run(session: AsyncSession, company_ids: list[UUID]) -> UUID:
    rules = RuleSetsRepo(session)
    rule_set = await rules.approve((await rules.propose({}, {})).id)
    workflow = await RunsRepo(session).create("job_search")
    run = await SearchRunsRepo(session).create(
        workflow_run_id=workflow.id,
        rule_set_id=rule_set.id,
        mode="rules_and_ai",
        company_order=company_ids,
    )
    return run.id


async def test_search_run_create_and_continue_cursor(db_session: AsyncSession) -> None:
    companies = [await add_company(db_session, f"C{i}", vendor="lever") for i in range(3)]
    run_id = await make_run(db_session, companies)
    repo = SearchRunsRepo(db_session)

    run = await repo.get(run_id)

    assert run is not None
    assert run.company_order == companies
    assert run.next_index == 0
    assert run.outcome is None


async def test_FR009_only_one_active_search(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session, [])
    repo = SearchRunsRepo(db_session)
    active = await repo.active()
    assert active is not None
    assert active.id == run_id

    with pytest.raises(IntegrityError):  # the database refuses a second queued/running search
        async with db_session.begin_nested():
            await RunsRepo(db_session).create("job_search")


async def test_request_stop_and_finish(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session, [])
    repo = SearchRunsRepo(db_session)

    await repo.request_stop(run_id)
    assert (await repo.get(run_id)).stop_requested is True  # type: ignore[union-attr]

    await repo.finish(run_id, outcome="out_of_credit", stop_message="No credit.", finished_at=T0)
    done = await repo.get(run_id)
    assert done is not None
    assert (done.outcome, done.stop_message, done.finished_at) == (
        "out_of_credit",
        "No credit.",
        T0,
    )


# --- possible duplicates ---------------------------------------------------------------------


async def test_possible_duplicate_pairs_are_stored_in_id_order(db_session: AsyncSession) -> None:
    a, b = await add_job(db_session, "One"), await add_job(db_session, "Two")
    repo = DuplicatesRepo(db_session)

    await repo.add(b, a, similarity=95)
    await repo.add(a, b, similarity=96)  # same pair again: kept once

    open_pairs = await repo.list_open()
    assert len(open_pairs) == 1
    pair = open_pairs[0]
    assert pair.job_a_id < pair.job_b_id
    await repo.set_status(pair.id, "dismissed", decided_at=T0)
    assert await repo.list_open() == []
