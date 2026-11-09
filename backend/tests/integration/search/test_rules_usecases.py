"""T019: propose, edit, approve and check search rules (US2, FR-004, FR-006)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.application.ports import ProposalFacts
from hiretitan.search.application.rules import (
    NoProposalError,
    RulesNotApprovedError,
    RulesService,
    RulesUnavailableError,
)
from hiretitan.search.domain.proposer import PlaceInput, ProposalInput
from hiretitan.search.domain.rules import RuleItem, RulesInvalidError
from hiretitan.search.infra.repos import RuleSetsRepo

T0 = datetime(2026, 11, 5, tzinfo=UTC)
SYNONYMS = {"backend engineer": ("backend developer",)}


@dataclass
class FakeSource:
    facts: ProposalFacts | None
    reason: str = "no_confirmed_profile"

    async def read(self) -> ProposalFacts:
        if self.facts is None:
            raise RulesUnavailableError(self.reason)  # type: ignore[arg-type]
        return self.facts


def make_facts(**changes: object) -> ProposalFacts:
    base = ProposalFacts(
        source=ProposalInput(
            target_roles=("Backend Engineer",),
            key_skills=("Python",),
            profile_skills=("Python", "Postgres"),
            preferred_locations=(PlaceInput("Bengaluru", "IN"),),
            blocked_locations=(PlaceInput("Pune", "IN"),),
            work_modes=frozenset({"remote"}),
            years_experience=Decimal(4),
        ),
        profile_version_id=uuid4(),
        preferences_saved_at=T0,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def service(session: AsyncSession, source: FakeSource) -> RulesService:
    return RulesService(RuleSetsRepo(session), source, SYNONYMS)


async def test_US2_AS2_approved_set_is_exactly_what_was_edited(db_session: AsyncSession) -> None:
    svc = service(db_session, FakeSource(make_facts()))
    proposal = await svc.propose()
    edited = replace(
        proposal.rules,
        title_avoid=(RuleItem("manager", "user"),),
        max_age_days=14,
    )

    await svc.edit_proposal(edited)
    approved = await svc.approve()

    assert approved.status == "approved"
    assert approved.rules == edited
    current, open_proposal = await svc.current()
    assert current is not None
    assert current.rules == edited
    assert open_proposal is None


async def test_US2_AS4_new_proposal_does_not_change_approved_set(db_session: AsyncSession) -> None:
    svc = service(db_session, FakeSource(make_facts()))
    await svc.propose()
    first = await svc.approve()

    again = await svc.propose()

    current, proposed = await svc.current()
    assert current is not None
    assert current.id == first.id
    assert current.rules == first.rules
    assert proposed is not None
    assert proposed.id == again.id
    assert proposed.status == "proposed"


async def test_FR004_one_approved_set_at_a_time(db_session: AsyncSession) -> None:
    svc = service(db_session, FakeSource(make_facts()))
    await svc.propose()
    first = await svc.approve()
    await svc.propose()
    second = await svc.approve()

    assert second.version > first.version
    repo = RuleSetsRepo(db_session)
    old = await repo.get(first.id)
    assert old is not None
    assert old.status == "superseded"
    approved = await repo.approved()
    assert approved is not None
    assert approved.id == second.id


async def test_FR006_profile_change_marks_rules_stale(db_session: AsyncSession) -> None:
    source = FakeSource(make_facts())
    svc = service(db_session, source)
    await svc.propose()
    await svc.approve()
    assert await svc.is_stale() is False

    source.facts = replace(source.facts, profile_version_id=uuid4())  # type: ignore[type-var]
    assert await svc.is_stale() is True


async def test_FR006_preferences_change_marks_rules_stale(db_session: AsyncSession) -> None:
    source = FakeSource(make_facts())
    svc = service(db_session, source)
    await svc.propose()
    await svc.approve()

    source.facts = replace(source.facts, preferences_saved_at=T0 + timedelta(days=1))  # type: ignore[type-var]
    assert await svc.is_stale() is True


async def test_no_approved_rules_are_never_stale(db_session: AsyncSession) -> None:
    assert await service(db_session, FakeSource(make_facts())).is_stale() is False


async def test_US2_AS5_search_start_needs_approved_rules(db_session: AsyncSession) -> None:
    svc = service(db_session, FakeSource(make_facts()))
    with pytest.raises(RulesNotApprovedError):
        await svc.require_approved()
    await svc.propose()
    with pytest.raises(RulesNotApprovedError):  # a proposal is not approval
        await svc.require_approved()
    await svc.approve()
    assert (await svc.require_approved()).status == "approved"


@pytest.mark.parametrize("reason", ["no_confirmed_profile", "no_preferences"])
async def test_proposal_reports_why_it_cannot_be_made(
    db_session: AsyncSession, reason: str
) -> None:
    svc = service(db_session, FakeSource(None, reason))
    with pytest.raises(RulesUnavailableError) as raised:
        await svc.propose()
    assert raised.value.reason == reason


async def test_FR002_edit_rejects_limit_violations(db_session: AsyncSession) -> None:
    svc = service(db_session, FakeSource(make_facts()))
    proposal = await svc.propose()
    bad = replace(proposal.rules, title_words=(), max_age_days=0)

    with pytest.raises(RulesInvalidError) as raised:
        await svc.edit_proposal(bad)

    assert {e.field for e in raised.value.errors} == {"title_words", "max_age_days"}
    _, still_open = await svc.current()
    assert still_open is not None
    assert still_open.rules == proposal.rules


async def test_edit_approve_and_discard_need_an_open_proposal(db_session: AsyncSession) -> None:
    svc = service(db_session, FakeSource(make_facts()))
    with pytest.raises(NoProposalError):
        await svc.approve()
    await svc.propose()
    await svc.discard_proposal()
    _, open_proposal = await svc.current()
    assert open_proposal is None
    with pytest.raises(NoProposalError):
        await svc.approve()


async def test_rules_round_trip_through_the_database(db_session: AsyncSession) -> None:
    svc = service(db_session, FakeSource(make_facts()))
    proposal = await svc.propose()
    _, reloaded = await svc.current()
    assert reloaded is not None
    assert reloaded.rules == proposal.rules
    assert reloaded.rules.years_experience == Decimal(4)
    assert isinstance(reloaded.id, UUID)
