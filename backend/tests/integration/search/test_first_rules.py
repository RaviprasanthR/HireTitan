"""002i T005: the first search rules are approved automatically, once (FR-001, FR-002, FR-004)."""

from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.search.application.ports import ProposalFacts
from hiretitan.search.application.rules import RulesService, RulesUnavailableError
from hiretitan.search.domain.proposer import PlaceInput, ProposalInput
from hiretitan.search.infra.models import SearchRuleSetRow
from hiretitan.search.infra.repos import RuleSetsRepo
from hiretitan.setup_wiring import SqlDeleteAllStore

T0 = datetime(2026, 11, 5, tzinfo=UTC)
SYNONYMS = {"backend engineer": ("backend developer",)}


@dataclass
class FakeSource:
    facts: ProposalFacts | None

    async def read(self) -> ProposalFacts:
        if self.facts is None:
            raise RulesUnavailableError("no_confirmed_profile")
        return self.facts


def make_facts(**changes: object) -> ProposalFacts:
    base = ProposalFacts(
        source=ProposalInput(
            target_roles=("Backend Engineer",),
            key_skills=("Python",),
            profile_skills=("Python", "Postgres"),
            preferred_locations=(PlaceInput("Bengaluru", "IN"),),
            work_modes=frozenset({"remote"}),
            years_experience=Decimal(4),
        ),
        profile_version_id=uuid4(),
        preferences_saved_at=T0,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def service(session: AsyncSession, facts: ProposalFacts | None = None) -> RulesService:
    return RulesService(RuleSetsRepo(session), FakeSource(facts or make_facts()), SYNONYMS)


async def count_rows(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(SearchRuleSetRow)) or 0


async def test_FR001_first_rules_are_approved(db_session: AsyncSession) -> None:
    outcome = await service(db_session).approve_first()

    assert outcome == "approved"
    approved = await RuleSetsRepo(db_session).approved()
    assert approved is not None
    assert approved.approved_by == "auto"
    assert approved.approved_at is not None
    assert approved.version == 1
    titles = [item["text"] for item in approved.rules["title_words"]]
    assert "Backend Engineer" in titles  # the proposal built from the preferences


async def test_FR002_existing_approval_is_never_replaced(db_session: AsyncSession) -> None:
    person = service(db_session)
    await person.propose()
    before = await person.approve()

    assert await person.approve_first() == "already"

    approved = await RuleSetsRepo(db_session).approved()
    assert approved is not None
    assert (approved.id, approved.version, approved.approved_by) == (before.id, 1, "person")
    assert await count_rows(db_session) == 1


async def test_FR002_a_superseded_approval_still_counts(db_session: AsyncSession) -> None:
    """The person approved twice; the first is superseded. Rules were approved once, so no more."""
    svc = service(db_session)
    await svc.propose()
    await svc.approve()
    await svc.propose()
    await svc.approve()
    assert await svc.approve_first() == "already"
    assert await count_rows(db_session) == 2


async def test_FR002_second_call_does_nothing(db_session: AsyncSession) -> None:
    svc = service(db_session)
    assert await svc.approve_first() == "approved"
    assert await svc.approve_first() == "already"
    assert await count_rows(db_session) == 1


async def test_FR002_double_finish_approves_once(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Two Finish presses at once (or Finish and start-up): exactly one approved rule set."""

    async def finish() -> str:
        async with sessions() as session:
            outcome = await service(session).approve_first()
            await asyncio.sleep(0.2)  # hold the transaction open so the other call has to wait
            await session.commit()
            return outcome

    outcomes = await asyncio.gather(finish(), finish())

    assert sorted(outcomes) == ["already", "approved"]
    async with sessions() as session:
        assert await count_rows(session) == 1
        approved = await RuleSetsRepo(session).approved()
        assert approved is not None
        assert approved.approved_by == "auto"


async def test_FR004_invalid_proposal_writes_nothing(db_session: AsyncSession) -> None:
    no_roles = make_facts(source=replace(make_facts().source, target_roles=()))

    assert await service(db_session, no_roles).approve_first() == "not_possible"
    assert await count_rows(db_session) == 0


async def test_FR004_missing_profile_writes_nothing(db_session: AsyncSession) -> None:
    svc = RulesService(RuleSetsRepo(db_session), FakeSource(None), SYNONYMS)

    assert await svc.approve_first() == "not_possible"
    assert await count_rows(db_session) == 0


async def test_FR002_runs_again_after_delete_all(db_session: AsyncSession) -> None:
    svc = service(db_session)
    assert await svc.approve_first() == "approved"

    await SqlDeleteAllStore(db_session).wipe_and_reseed()
    assert await count_rows(db_session) == 0

    assert await service(db_session).approve_first() == "approved"
    approved = await RuleSetsRepo(db_session).approved()
    assert approved is not None
    assert approved.approved_by == "auto"


def test_FR007_first_approval_makes_no_llm_call() -> None:
    """The use case is built from the proposer and the store only; it cannot reach a model."""
    source = Path(__file__).parents[3] / "src/hiretitan/search/application/rules.py"
    imported = {
        node.module or ""
        for node in ast.walk(ast.parse(source.read_text("utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert not [module for module in imported if "llm" in module or "prompts" in module]
