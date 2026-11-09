"""T025: the free rules that skip obvious noise (US1 AS3, AS4, FR-027)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hiretitan.search.domain.apply_rules import Pass, RuleJob, Skip, apply
from hiretitan.search.domain.rules import LocationRule, RuleItem, SearchRules

NOW = datetime(2026, 11, 6, tzinfo=UTC)
SYNONYMS = {"backend engineer": ("backend developer", "server side engineer")}


def rules(**changes: object) -> SearchRules:
    base = SearchRules(
        title_words=(RuleItem("Backend Engineer", "user"),),
        title_avoid=(RuleItem("intern", "user"),),
        blocked_locations=(LocationRule("Pune", "IN", "user"),),
        max_age_days=30,
    )
    from dataclasses import replace

    return replace(base, **changes)  # type: ignore[arg-type]


def job(**changes: object) -> RuleJob:
    base = {
        "title": "Senior Backend Engineer",
        "city": "Bengaluru",
        "country": "IN",
        "location_text": "Bengaluru, India",
        "posted_at": NOW - timedelta(days=2),
    }
    return RuleJob(**{**base, **changes})  # type: ignore[arg-type]


def test_matching_job_passes() -> None:
    assert apply(job(), rules(), NOW, SYNONYMS) == Pass()


def test_US1_AS3_unrelated_title_skipped_with_reason() -> None:
    result = apply(job(title="HR Business Partner"), rules(), NOW, SYNONYMS)
    assert result == Skip("title_words", "title matches none of your roles")


def test_synonym_title_passes() -> None:
    assert apply(job(title="Server-side Engineer"), rules(), NOW, SYNONYMS) == Pass()
    assert apply(job(title="Backend Developer (Python)"), rules(), NOW, SYNONYMS) == Pass()


def test_synonym_not_used_without_the_table() -> None:
    assert isinstance(apply(job(title="Backend Developer"), rules(), NOW), Skip)


def test_avoid_word_skips() -> None:
    result = apply(job(title="Backend Engineer Intern"), rules(), NOW, SYNONYMS)
    assert result == Skip("title_avoid", "title contains 'intern', a word you avoid")


def test_avoid_word_needs_a_whole_word() -> None:
    assert apply(job(title="Backend Engineer, Internal Tools"), rules(), NOW, SYNONYMS) == Pass()


def test_US1_AS4_blocked_location_skipped() -> None:
    result = apply(job(city="Pune", location_text="Pune"), rules(), NOW, SYNONYMS)
    assert result == Skip("blocked_locations", "location Pune is in your blocked list")


def test_blocked_location_is_alias_aware() -> None:
    blocked = rules(blocked_locations=(LocationRule("Bangalore", None, "user"),))
    assert isinstance(apply(job(), blocked, NOW, SYNONYMS), Skip)


def test_blocked_country_skips() -> None:
    blocked = rules(blocked_locations=(LocationRule(None, "US", "user"),))
    result = apply(job(city="New York", country="US"), blocked, NOW, SYNONYMS)
    assert result == Skip("blocked_locations", "location US is in your blocked list")


def test_blocked_city_found_in_text_when_city_not_parsed() -> None:
    result = apply(
        job(city=None, country=None, location_text="Poona office"), rules(), NOW, SYNONYMS
    )
    assert isinstance(result, Skip)


def test_FR027_no_location_never_skipped() -> None:
    result = apply(job(city=None, country=None, location_text=None), rules(), NOW, SYNONYMS)
    assert result == Pass()


def test_FR027_no_date_never_skipped() -> None:
    assert apply(job(posted_at=None), rules(), NOW, SYNONYMS) == Pass()


def test_age_limit() -> None:
    old = job(posted_at=NOW - timedelta(days=31))
    assert apply(old, rules(), NOW, SYNONYMS) == Skip(
        "max_age_days", "posted more than 30 days ago"
    )
    assert apply(job(posted_at=NOW - timedelta(days=30)), rules(), NOW, SYNONYMS) == Pass()


def test_first_failing_rule_wins_in_a_stable_order() -> None:
    result = apply(job(title="Sales Intern", city="Pune"), rules(), NOW, SYNONYMS)
    assert result == Skip("title_words", "title matches none of your roles")
