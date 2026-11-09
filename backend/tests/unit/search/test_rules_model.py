"""T008: the search rules and their limits (data-model.md, FR-005)."""

from __future__ import annotations

import pytest

from hiretitan.search.domain.rules import (
    EFFECTS,
    LocationRule,
    RuleItem,
    RulesInvalidError,
    SearchRules,
)


def words(n: int, length: int = 5) -> tuple[RuleItem, ...]:
    return tuple(RuleItem(f"{i:0{length}d}", "user") for i in range(n))


def places(n: int) -> tuple[LocationRule, ...]:
    return tuple(LocationRule(f"City{i}", "IN", "user") for i in range(n))


def fields_failing(**overrides: object) -> set[str]:
    base: dict[str, object] = {"title_words": words(1)}
    with pytest.raises(RulesInvalidError) as caught:
        SearchRules(**{**base, **overrides}).validate()  # type: ignore[arg-type]
    return {error.field for error in caught.value.errors}


def test_a_minimal_rule_set_is_valid() -> None:
    rules = SearchRules(title_words=words(1))
    rules.validate()
    assert rules.max_age_days == 30  # default


def test_title_words_need_at_least_one() -> None:
    assert fields_failing(title_words=()) == {"title_words"}


def test_title_words_at_most_30() -> None:
    SearchRules(title_words=words(30)).validate()
    assert fields_failing(title_words=words(31)) == {"title_words"}


def test_title_word_at_most_60_chars() -> None:
    SearchRules(title_words=(RuleItem("x" * 60, "user"),)).validate()
    assert fields_failing(title_words=(RuleItem("x" * 61, "user"),)) == {"title_words"}


def test_blank_item_rejected() -> None:
    assert fields_failing(title_words=(RuleItem("  ", "user"),)) == {"title_words"}


def test_title_avoid_at_most_30() -> None:
    SearchRules(title_words=words(1), title_avoid=words(30)).validate()
    assert fields_failing(title_avoid=words(31)) == {"title_avoid"}


def test_blocked_locations_at_most_30() -> None:
    SearchRules(title_words=words(1), blocked_locations=places(30)).validate()
    assert fields_failing(blocked_locations=places(31)) == {"blocked_locations"}


def test_stack_keywords_at_most_50() -> None:
    SearchRules(title_words=words(1), stack_keywords=words(50)).validate()
    assert fields_failing(stack_keywords=words(51)) == {"stack_keywords"}


def test_preferred_locations_at_most_30() -> None:
    SearchRules(title_words=words(1), preferred_locations=places(30)).validate()
    assert fields_failing(preferred_locations=places(31)) == {"preferred_locations"}


@pytest.mark.parametrize("days", [0, 366, -5])
def test_max_age_days_between_1_and_365(days: int) -> None:
    assert fields_failing(max_age_days=days) == {"max_age_days"}


@pytest.mark.parametrize("days", [1, 365])
def test_max_age_days_edges_are_valid(days: int) -> None:
    SearchRules(title_words=words(1), max_age_days=days).validate()


def test_work_modes_must_be_known() -> None:
    SearchRules(title_words=words(1), work_modes=frozenset({"onsite", "remote"})).validate()
    assert fields_failing(work_modes=frozenset({"office"})) == {"work_modes"}


@pytest.mark.parametrize("years", ["-1", "51"])
def test_years_experience_between_0_and_50(years: str) -> None:
    from decimal import Decimal

    assert fields_failing(years_experience=Decimal(years)) == {"years_experience"}


def test_years_experience_may_be_null() -> None:
    SearchRules(title_words=words(1), years_experience=None).validate()


@pytest.mark.parametrize(
    "origin",
    ["preference:target_roles", "profile:skills", "synonym_table", "user"],
)
def test_known_origins_are_valid(origin: str) -> None:
    SearchRules(title_words=(RuleItem("backend", origin),)).validate()


@pytest.mark.parametrize("origin", ["", "guess", "preference:", "profile", "ai"])
def test_unknown_origin_rejected(origin: str) -> None:
    assert fields_failing(title_words=(RuleItem("backend", origin),)) == {"title_words"}


def test_all_problems_are_reported_together() -> None:
    assert fields_failing(title_words=(), max_age_days=0) == {"title_words", "max_age_days"}


def test_FR005_each_rule_declares_its_effect() -> None:
    assert EFFECTS == {
        "title_words": "skips",
        "title_avoid": "skips",
        "blocked_locations": "skips",
        "max_age_days": "skips",
        "stack_keywords": "guides_ai",
        "preferred_locations": "guides_ai",
        "work_modes": "guides_ai",
        "seniority": "guides_ai",
        "years_experience": "guides_ai",
    }
