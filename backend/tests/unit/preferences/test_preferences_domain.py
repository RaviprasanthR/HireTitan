"""T052: preferences domain (FR-023 to FR-026, US2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from hiretitan.preferences.domain.defaults import (
    DEFAULT_COUNTRY,
    annual_to_lpa,
    default_preferences,
    lpa_to_annual,
)
from hiretitan.preferences.domain.model import Pay, Place, Preferences
from hiretitan.preferences.domain.rules import save_errors


def valid(**changes: object) -> Preferences:
    fields: dict[str, object] = {"target_roles": ("Backend Engineer",), **changes}
    return replace(default_preferences(), **fields)  # type: ignore[arg-type]


def paths(prefs: Preferences) -> set[str]:
    return {e.path for e in save_errors(prefs)}


def test_FR024_defaults_documented_and_neutral() -> None:
    d = default_preferences()
    assert d.target_roles == ()
    assert d.seniority_levels == ()
    assert d.years_experience is None
    assert d.key_skills == ()
    assert d.preferred_locations == ()
    assert d.default_country == DEFAULT_COUNTRY == "IN"
    assert d.work_modes == frozenset({"onsite", "hybrid", "remote"})
    assert d.willing_to_relocate is False
    assert d.blocked_locations == ()
    assert d.job_types == frozenset({"full_time"})
    assert d.pay == Pay(currency="INR", min_annual=None, target_annual=None, basis="fixed")
    assert d.notice_period_days == 30
    assert d.earliest_start_date is None
    assert d.preferred_companies == ()
    assert d.avoided_companies == ()


def test_valid_preferences_have_no_errors() -> None:
    assert save_errors(valid()) == []


def test_US2_AS4_empty_roles_rejected() -> None:
    errors = save_errors(default_preferences())
    assert [e.path for e in errors] == ["target_roles"]
    assert "role" in errors[0].message.lower()
    assert "target_roles" in paths(replace(valid(), target_roles=("  ",)))


def test_US2_AS4_min_above_target_rejected() -> None:
    prefs = valid(pay=Pay("INR", Decimal(2_000_000), Decimal(1_000_000), "fixed"))
    assert paths(prefs) == {"pay.min_annual"}
    ok = valid(pay=Pay("INR", Decimal(1_000_000), Decimal(1_000_000), "fixed"))
    assert save_errors(ok) == []


def test_pay_must_not_be_negative_and_currency_must_be_iso() -> None:
    assert "pay.min_annual" in paths(valid(pay=Pay("INR", Decimal(-1), None, "fixed")))
    assert "pay.target_annual" in paths(valid(pay=Pay("INR", None, Decimal(-5), "fixed")))
    assert "pay.currency" in paths(valid(pay=Pay("RUPEES", None, None, "fixed")))
    assert "pay.basis" in paths(valid(pay=Pay("INR", None, None, "gross")))  # type: ignore[arg-type]


def test_FR025_negative_years_rejected() -> None:
    assert paths(valid(years_experience=Decimal(-1))) == {"years_experience"}
    assert paths(valid(years_experience=Decimal(61))) == {"years_experience"}
    assert paths(valid(years_experience=Decimal("2.3"))) == {"years_experience"}  # step 0.5
    assert save_errors(valid(years_experience=Decimal("2.5"))) == []
    assert save_errors(valid(years_experience=Decimal(0))) == []


def test_notice_xor_start_date() -> None:
    both = valid(notice_period_days=30, earliest_start_date=date(2027, 1, 1))
    assert paths(both) == {"notice_period_days"}
    assert save_errors(valid(notice_period_days=None, earliest_start_date=date(2027, 1, 1))) == []
    assert save_errors(valid(notice_period_days=None, earliest_start_date=None)) == []
    assert paths(valid(notice_period_days=366)) == {"notice_period_days"}
    assert paths(valid(notice_period_days=-1)) == {"notice_period_days"}


def test_US2_AS5_lpa_conversion() -> None:
    assert lpa_to_annual(Decimal("18.5")) == Decimal(1_850_000)
    assert annual_to_lpa(Decimal(1_850_000)) == Decimal("18.5")
    assert annual_to_lpa(lpa_to_annual(Decimal("12.34"))) == Decimal("12.34")


def test_sets_and_enums_are_checked() -> None:
    assert paths(valid(work_modes=frozenset())) == {"work_modes"}
    assert paths(valid(work_modes=frozenset({"office"}))) == {"work_modes"}
    assert paths(valid(job_types=frozenset())) == {"job_types"}
    assert paths(valid(job_types=frozenset({"gig"}))) == {"job_types"}
    assert paths(valid(seniority_levels=("wizard",))) == {"seniority_levels"}
    assert save_errors(valid(seniority_levels=("senior", "lead"))) == []


def test_lists_are_bounded_and_skills_unique() -> None:
    assert paths(valid(target_roles=tuple(f"Role {i}" for i in range(21)))) == {"target_roles"}
    assert paths(valid(target_roles=("x" * 101,))) == {"target_roles"}
    assert paths(valid(key_skills=("Python", " python "))) == {"key_skills"}
    assert paths(valid(key_skills=tuple(f"s{i}" for i in range(51)))) == {"key_skills"}
    assert paths(valid(key_skills=("x" * 81,))) == {"key_skills"}
    assert paths(valid(preferred_companies=tuple(f"c{i}" for i in range(101)))) == {
        "preferred_companies"
    }
    assert paths(valid(avoided_companies=("x" * 201,))) == {"avoided_companies"}


def test_locations_use_iso_countries_and_are_bounded() -> None:
    assert save_errors(valid(preferred_locations=(Place("Pune", "IN"), Place(None, "DE")))) == []
    assert paths(valid(preferred_locations=(Place("Pune", "ZZ"),))) == {"preferred_locations"}
    assert paths(valid(blocked_locations=(Place("Pune", "in"),))) == {"blocked_locations"}
    assert paths(valid(preferred_locations=(Place("x", "IN"),) * 21)) == {"preferred_locations"}
    assert paths(valid(blocked_locations=(Place("x", "IN"),) * 51)) == {"blocked_locations"}
    assert paths(valid(default_country="XX")) == {"default_country"}
