"""T029: starting, stopping and writing batches of a search (FR-004, FR-008, FR-009)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.application.ports import ProposalFacts
from hiretitan.search.application.rules import RulesNotApprovedError, RulesService
from hiretitan.search.application.search import (
    BatchWrite,
    CompanyOutcome,
    DecisionInput,
    NewJob,
    SearchAlreadyRunningError,
    SearchNotRunningError,
    SeenJob,
    SetupIncompleteError,
    request_stop,
    start_search,
    store_batch,
)
from hiretitan.search.domain.proposer import ProposalInput
from hiretitan.search.infra.models import (
    JobRow,
    JobSourceRow,
    PossibleDuplicateRow,
    RelevanceDecisionRow,
    SearchRunCompanyRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo, RuleSetsRepo, SearchRunsRepo
from hiretitan.search.infra.search_store import SearchStore

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)


@dataclass
class FakeSource:
    async def read(self) -> ProposalFacts:
        return ProposalFacts(ProposalInput(target_roles=("Backend Engineer",)), uuid4(), NOW)


@dataclass
class FakeSetup:
    complete: bool = True

    async def setup_complete(self) -> bool:
        return self.complete


@dataclass
class FakeQueue:
    run_ids: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.run_ids.append(run_id)


def rules_service(session: AsyncSession) -> RulesService:
    return RulesService(RuleSetsRepo(session), FakeSource(), {})


async def approve_rules(session: AsyncSession) -> None:
    svc = rules_service(session)
    await svc.propose()
    await svc.approve()


async def start(session: AsyncSession, queue: FakeQueue, *, setup: FakeSetup | None = None):  # type: ignore[no-untyped-def]
    return await start_search(
        "rules_and_ai",
        rules=rules_service(session),
        setup=setup or FakeSetup(),
        store=SearchStore(session),
        queue=queue,
        now=NOW,
    )


async def test_FR004_start_needs_approved_rules(db_session: AsyncSession) -> None:
    queue = FakeQueue()
    with pytest.raises(RulesNotApprovedError):
        await start(db_session, queue)
    assert queue.run_ids == []


async def test_US1_AS11_start_needs_setup_complete(db_session: AsyncSession) -> None:
    await approve_rules(db_session)
    queue = FakeQueue()
    with pytest.raises(SetupIncompleteError):
        await start(db_session, queue, setup=FakeSetup(False))
    assert queue.run_ids == []


async def test_start_creates_run_and_enqueues_it(db_session: AsyncSession) -> None:
    await approve_rules(db_session)
    queue = FakeQueue()

    started = await start(db_session, queue)

    assert queue.run_ids == [started.run_id]
    run = await SearchRunsRepo(db_session).get(started.search_run_id)
    assert run is not None
    assert (run.mode, run.outcome, run.next_index, run.batches_done) == (
        "rules_and_ai",
        None,
        0,
        0,
    )
    approved = await RuleSetsRepo(db_session).approved()
    assert approved is not None
    assert run.rule_set_id == approved.id


async def test_FR009_second_search_conflicts(db_session: AsyncSession) -> None:
    await approve_rules(db_session)
    queue = FakeQueue()
    await start(db_session, queue)

    with pytest.raises(SearchAlreadyRunningError):
        await start(db_session, queue)
    assert len(queue.run_ids) == 1


async def test_stop_sets_the_flag_and_needs_a_running_search(db_session: AsyncSession) -> None:
    await approve_rules(db_session)
    started = await start(db_session, FakeQueue())
    store = SearchStore(db_session)

    await request_stop(store, started.search_run_id)

    run = await SearchRunsRepo(db_session).get(started.search_run_id)
    assert run is not None
    assert run.stop_requested is True
    with pytest.raises(SearchNotRunningError):
        await request_stop(store, uuid4())


# --- batches ---------------------------------------------------------------------------------


def new_job(title: str = "Backend Engineer", **changes: object) -> NewJob:
    base: dict[str, Any] = {
        "company_id": None,
        "company_name": "Acme",
        "title": title,
        "location_text": "Pune, India",
        "city": "Pune",
        "country": "IN",
        "work_mode": None,
        "posted_at": None,
        "description": "Build things.",
        "skills_found": ("Python",),
        "years_found": Decimal(3),
        "canonical_url": f"https://boards.example.com/acme/{title.replace(' ', '-')}",
        "ats_vendor": "lever",
        "requisition_id": None,
        "source_url": f"https://boards.example.com/acme/{title.replace(' ', '-')}",
        "injection_flags": [],
        "decision": DecisionInput("shown", "ai", "Fits the role", provenance={"model": "m"}),
        "candidates": (),
    }
    return NewJob(**{**base, **changes})


async def started_run(session: AsyncSession) -> UUID:
    await approve_rules(session)
    return (await start(session, FakeQueue())).search_run_id


async def add_company(session: AsyncSession, name: str) -> UUID:
    company = await CompaniesRepo(session).add(
        name=name, origin="user", resolution="verified", ats_vendor="lever", board_id="b"
    )
    return company.id


async def test_batch_writes_jobs_decisions_sources_and_counts(db_session: AsyncSession) -> None:
    run_id = await started_run(db_session)
    company = await add_company(db_session, "Acme")
    store = SearchStore(db_session)

    result = await store_batch(
        store,
        BatchWrite(
            search_run_id=run_id,
            batch_no=1,
            new=[
                new_job("Backend Engineer", company_id=company),
                new_job(
                    "Sales Rep",
                    company_id=company,
                    decision=DecisionInput(
                        "skipped",
                        "rule",
                        "title matches none of your roles",
                        rule_key="title_words",
                    ),
                ),
                new_job(
                    "Python Developer",
                    company_id=company,
                    decision=DecisionInput("shown", "rules_only_fallback", "not checked by AI"),
                ),
            ],
            seen=[],
            companies=[CompanyOutcome(company, "ok", 3, None)],
            next_index=1,
            now=NOW,
        ),
    )

    assert (result.added, result.skipped_by_rules) == (2, 1)
    states = {r.title: r.state for r in (await db_session.scalars(select(JobRow))).all()}
    assert states == {
        "Backend Engineer": "explore",
        "Sales Rep": "skipped",
        "Python Developer": "explore",
    }
    decisions = (await db_session.scalars(select(RelevanceDecisionRow))).all()
    assert {(d.decided_by, d.is_current) for d in decisions} == {
        ("ai", True),
        ("rule", True),
        ("rules_only_fallback", True),
    }
    assert await db_session.scalar(select(func.count()).select_from(JobSourceRow)) == 3
    row = (await db_session.scalars(select(SearchRunCompanyRow))).one()
    assert (row.result, row.jobs_found, row.batch_no) == ("ok", 3, 1)

    run = await SearchRunsRepo(db_session).get(run_id)
    assert run is not None
    assert (run.batches_done, run.next_index) == (1, 1)
    assert (run.jobs_found, run.skipped_by_rules, run.judged_by_ai) == (3, 1, 1)
    assert (run.kept, run.added, run.merged, run.not_checked_by_ai) == (2, 2, 0, 1)


async def test_seen_again_job_keeps_state_and_gets_a_source(db_session: AsyncSession) -> None:
    run_id = await started_run(db_session)
    store = SearchStore(db_session)
    await store_batch(
        store,
        BatchWrite(run_id, 1, [new_job("Backend Engineer")], [], [], 0, NOW),
    )
    job = (await db_session.scalars(select(JobRow))).one()
    await JobsRepo(db_session).set_state(job.id, "skipped")  # the person restored/skipped it

    later = datetime(2026, 11, 7, tzinfo=UTC)
    result = await store_batch(
        store,
        BatchWrite(
            run_id,
            2,
            [],
            [SeenJob(job.id, "https://careers.example.com/backend-engineer", "careers_page")],
            [],
            1,
            later,
        ),
    )

    assert (result.merged, result.added) == (1, 0)
    await db_session.refresh(job)
    assert job.state == "skipped"  # FR-026: nothing is decided again
    assert job.last_seen_at == later
    assert job.listed is True
    assert await db_session.scalar(select(func.count()).select_from(JobSourceRow)) == 2
    assert await db_session.scalar(select(func.count()).select_from(RelevanceDecisionRow)) == 1


async def test_candidate_pairs_are_stored_in_id_order(db_session: AsyncSession) -> None:
    run_id = await started_run(db_session)
    store = SearchStore(db_session)
    await store_batch(store, BatchWrite(run_id, 1, [new_job("Backend Engineer")], [], [], 0, NOW))
    first = (await db_session.scalars(select(JobRow))).one()

    await store_batch(
        store,
        BatchWrite(
            run_id,
            2,
            [new_job("Backend Engineer II", candidates=((first.id, 95.0),))],
            [],
            [],
            0,
            NOW,
        ),
    )

    pair = (await db_session.scalars(select(PossibleDuplicateRow))).one()
    assert pair.job_a_id < pair.job_b_id
    assert {pair.job_a_id, pair.job_b_id} >= {first.id}
    assert pair.status == "open"


async def test_FR008_batch_commit_is_atomic(db_session: AsyncSession) -> None:
    run_id = await started_run(db_session)
    store = SearchStore(db_session)
    bad = new_job("Broken", decision=DecisionInput("shown", "ai", ""))  # reason must not be empty

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await store_batch(
                store,
                BatchWrite(
                    run_id,
                    1,
                    [new_job("Backend Engineer"), bad],
                    [],
                    [],
                    5,
                    NOW,
                ),
            )

    assert await db_session.scalar(select(func.count()).select_from(JobRow)) == 0
    assert await db_session.scalar(select(func.count()).select_from(RelevanceDecisionRow)) == 0
    run = await SearchRunsRepo(db_session).get(run_id)
    assert run is not None
    assert (run.batches_done, run.next_index) == (0, 0)
