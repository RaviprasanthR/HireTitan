"""T018: the deterministic rule proposer (research R9, US2, FR-001, FR-005)."""

from __future__ import annotations

from decimal import Decimal

from hiretitan.search.domain.proposer import PlaceInput, ProposalInput, propose_rules
from hiretitan.search.domain.rules import (
    STACK_KEYWORDS_MAX,
    TITLE_WORDS_MAX,
    SearchRules,
)

TABLE = {
    "backend engineer": ("backend developer", "back end engineer"),
    "data engineer": ("etl developer",),
}


def _input(**changes: object) -> ProposalInput:
    base = ProposalInput(
        target_roles=("Backend Engineer",),
        seniority_levels=("mid",),
        years_experience=Decimal(4),
        key_skills=("Python",),
        profile_skills=("FastAPI", "python", "Postgres", "FastAPI", "FastAPI", "Postgres"),
        preferred_locations=(PlaceInput(city="Bengaluru", country="IN"),),
        blocked_locations=(PlaceInput(city="Pune", country="IN"),),
        work_modes=frozenset({"remote", "hybrid"}),
    )
    from dataclasses import replace

    return replace(base, **changes)  # type: ignore[arg-type]


def test_FR001_all_rule_kinds_proposed() -> None:
    rules = propose_rules(_input(), TABLE)
    assert [i.text for i in rules.title_words][:1] == ["Backend Engineer"]
    assert rules.stack_keywords
    assert rules.preferred_locations[0].city == "Bengaluru"
    assert rules.blocked_locations[0].city == "Pune"
    assert rules.work_modes == frozenset({"remote", "hybrid"})
    assert rules.seniority == ("mid",)
    assert rules.years_experience == Decimal(4)
    assert rules.max_age_days == 30
    rules.validate()


def test_US2_AS1_every_rule_has_an_origin() -> None:
    rules = propose_rules(_input(), TABLE)
    items = [*rules.title_words, *rules.stack_keywords]
    places = [*rules.preferred_locations, *rules.blocked_locations]
    assert all(i.origin for i in items)
    assert all(p.origin for p in places)
    assert rules.title_words[0].origin == "preference:target_roles[0]"
    assert {i.origin for i in rules.title_words[1:]} == {"synonym_table"}
    assert rules.stack_keywords[0].origin == "preference:key_skills[0]"
    assert rules.preferred_locations[0].origin == "preference:preferred_locations[0]"
    assert rules.blocked_locations[0].origin == "preference:blocked_locations[0]"


def test_synonyms_are_added_after_their_role_without_repeats() -> None:
    rules = propose_rules(_input(target_roles=("Backend Engineer", "backend developer")), TABLE)
    texts = [i.text.lower() for i in rules.title_words]
    assert texts == ["backend engineer", "backend developer", "back end engineer"]


def test_US2_AS3_proposal_needs_no_ai() -> None:
    # the proposer is a pure function of its two inputs: same input, same output
    assert propose_rules(_input(), TABLE) == propose_rules(_input(), TABLE)


def test_FR005_avoid_words_empty_until_person_adds_some() -> None:
    assert propose_rules(_input(), TABLE).title_avoid == ()


def test_profile_skills_most_frequent_first_after_key_skills_without_repeats() -> None:
    rules = propose_rules(_input(), TABLE)
    assert [i.text for i in rules.stack_keywords] == ["Python", "FastAPI", "Postgres"]
    assert rules.stack_keywords[1].origin == "profile:skills"


def test_proposal_respects_item_limits() -> None:
    many_roles = tuple(f"Role {i}" for i in range(TITLE_WORDS_MAX + 5))
    many_skills = tuple(f"skill{i}" for i in range(STACK_KEYWORDS_MAX + 20))
    rules = propose_rules(_input(target_roles=many_roles, profile_skills=many_skills), TABLE)
    assert len(rules.title_words) == TITLE_WORDS_MAX
    assert len(rules.stack_keywords) == STACK_KEYWORDS_MAX
    rules.validate()


def test_roles_come_before_synonyms_when_the_limit_cuts() -> None:
    roles = tuple(f"Role {i}" for i in range(TITLE_WORDS_MAX))
    rules = propose_rules(_input(target_roles=(*roles, "Backend Engineer")), TABLE)
    assert all(i.origin != "synonym_table" for i in rules.title_words)


def test_no_target_roles_gives_no_title_words() -> None:
    rules = propose_rules(_input(target_roles=()), TABLE)
    assert rules == SearchRules(
        stack_keywords=rules.stack_keywords,
        preferred_locations=rules.preferred_locations,
        blocked_locations=rules.blocked_locations,
        work_modes=rules.work_modes,
        seniority=rules.seniority,
        years_experience=rules.years_experience,
    )
