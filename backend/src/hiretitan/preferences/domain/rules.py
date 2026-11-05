"""Rules a preferences form must pass to be saved (FR-025). Pure.

All problems are reported together, each with the path of the field to mark.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hiretitan.preferences.domain.defaults import (
    JOB_TYPES,
    PAY_BASES,
    SENIORITY_LEVELS,
    WORK_MODES,
)
from hiretitan.preferences.domain.iso import COUNTRIES, CURRENCIES
from hiretitan.preferences.domain.model import Place, Preferences

MAX_ROLES, MAX_ROLE = 20, 100
MAX_SKILLS, MAX_SKILL = 50, 80
MAX_PREFERRED_PLACES, MAX_BLOCKED_PLACES, MAX_CITY = 20, 50, 120
MAX_COMPANIES, MAX_COMPANY = 100, 200
MAX_YEARS = Decimal(60)
MAX_NOTICE_DAYS = 365


@dataclass(frozen=True, slots=True)
class FieldError:
    path: str
    message: str


def _strings(
    path: str, label: str, items: tuple[str, ...], max_items: int, max_len: int
) -> list[FieldError]:
    if len(items) > max_items:
        return [FieldError(path, f"At most {max_items} {label}")]
    if any(not item.strip() for item in items):
        return [FieldError(path, f"Empty entries are not allowed in {label}")]
    if any(len(item) > max_len for item in items):
        return [FieldError(path, f"Each entry must be at most {max_len} characters")]
    return []


def _places(path: str, places: tuple[Place, ...], maximum: int) -> list[FieldError]:
    if len(places) > maximum:
        return [FieldError(path, f"At most {maximum} locations")]
    if any(p.country not in COUNTRIES for p in places):
        return [FieldError(path, "Use a valid two-letter country code")]
    if any(p.city is not None and len(p.city) > MAX_CITY for p in places):
        return [FieldError(path, f"City names must be at most {MAX_CITY} characters")]
    return []


def _skill_errors(skills: tuple[str, ...]) -> list[FieldError]:
    errors = _strings("key_skills", "skills", skills, MAX_SKILLS, MAX_SKILL)
    if errors:
        return errors
    keys = [" ".join(s.split()).casefold() for s in skills]
    if len(keys) != len(set(keys)):
        return [FieldError("key_skills", "Each skill can appear only once")]
    return []


def _pay_errors(prefs: Preferences) -> list[FieldError]:
    pay = prefs.pay
    errors: list[FieldError] = []
    if pay.currency not in CURRENCIES:
        errors.append(FieldError("pay.currency", "Use a valid three-letter currency code"))
    if pay.basis not in PAY_BASES:
        errors.append(FieldError("pay.basis", "Choose fixed or total pay"))
    if pay.min_annual is not None and pay.min_annual < 0:
        errors.append(FieldError("pay.min_annual", "Pay cannot be negative"))
    if pay.target_annual is not None and pay.target_annual < 0:
        errors.append(FieldError("pay.target_annual", "Pay cannot be negative"))
    if (
        pay.min_annual is not None
        and pay.target_annual is not None
        and pay.min_annual >= 0
        and pay.min_annual > pay.target_annual
    ):
        errors.append(FieldError("pay.min_annual", "Minimum pay cannot be above the target"))
    return errors


def _years_errors(years: Decimal | None) -> list[FieldError]:
    if years is None:
        return []
    if years < 0 or years > MAX_YEARS:
        return [FieldError("years_experience", "Years of experience must be between 0 and 60")]
    if (years * 2) % 1 != 0:
        return [FieldError("years_experience", "Use steps of half a year")]
    return []


def _notice_errors(prefs: Preferences) -> list[FieldError]:
    days = prefs.notice_period_days
    if days is None:
        return []
    if not 0 <= days <= MAX_NOTICE_DAYS:
        return [FieldError("notice_period_days", "Notice period must be 0 to 365 days")]
    if prefs.earliest_start_date is not None:
        return [FieldError("notice_period_days", "Give a notice period or a start date, not both")]
    return []


def save_errors(prefs: Preferences) -> list[FieldError]:
    """Every reason these preferences cannot be saved; empty means they can."""
    errors: list[FieldError] = []
    if not any(role.strip() for role in prefs.target_roles):
        errors.append(FieldError("target_roles", "Add at least one target role"))
    else:
        errors += _strings("target_roles", "roles", prefs.target_roles, MAX_ROLES, MAX_ROLE)
    if any(level not in SENIORITY_LEVELS for level in prefs.seniority_levels):
        errors.append(FieldError("seniority_levels", "Choose from the listed levels"))
    errors += _years_errors(prefs.years_experience)
    errors += _skill_errors(prefs.key_skills)
    errors += _places("preferred_locations", prefs.preferred_locations, MAX_PREFERRED_PLACES)
    errors += _places("blocked_locations", prefs.blocked_locations, MAX_BLOCKED_PLACES)
    if prefs.default_country not in COUNTRIES:
        errors.append(FieldError("default_country", "Use a valid two-letter country code"))
    if not prefs.work_modes or not prefs.work_modes <= set(WORK_MODES):
        errors.append(FieldError("work_modes", "Choose at least one work mode"))
    if not prefs.job_types or not prefs.job_types <= set(JOB_TYPES):
        errors.append(FieldError("job_types", "Choose at least one job type"))
    errors += _pay_errors(prefs)
    errors += _notice_errors(prefs)
    for path, items in (
        ("preferred_companies", prefs.preferred_companies),
        ("avoided_companies", prefs.avoided_companies),
    ):
        errors += _strings(path, "companies", items, MAX_COMPANIES, MAX_COMPANY)
    return errors
