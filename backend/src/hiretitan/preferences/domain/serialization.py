"""Preferences <-> plain JSON (for the jsonb column and the API). Pure.

Reading is tolerant: a missing key takes its documented default, so a row saved by an older
version still loads. Money and years travel as strings to keep their exact decimal value.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from hiretitan.preferences.domain.defaults import default_preferences
from hiretitan.preferences.domain.model import Pay, Place, Preferences

Json = dict[str, Any]


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _dec_from(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _place_to(place: Place) -> Json:
    return {"city": place.city, "country": place.country}


def _place_from(data: Json) -> Place:
    return Place(data.get("city"), data["country"])


def preferences_to_json(prefs: Preferences) -> Json:
    return {
        "target_roles": list(prefs.target_roles),
        "seniority_levels": list(prefs.seniority_levels),
        "years_experience": _dec(prefs.years_experience),
        "key_skills": list(prefs.key_skills),
        "preferred_locations": [_place_to(p) for p in prefs.preferred_locations],
        "default_country": prefs.default_country,
        "work_modes": sorted(prefs.work_modes),
        "willing_to_relocate": prefs.willing_to_relocate,
        "blocked_locations": [_place_to(p) for p in prefs.blocked_locations],
        "job_types": sorted(prefs.job_types),
        "pay": {
            "currency": prefs.pay.currency,
            "min_annual": _dec(prefs.pay.min_annual),
            "target_annual": _dec(prefs.pay.target_annual),
            "basis": prefs.pay.basis,
        },
        "notice_period_days": prefs.notice_period_days,
        "earliest_start_date": (
            prefs.earliest_start_date.isoformat() if prefs.earliest_start_date else None
        ),
        "preferred_companies": list(prefs.preferred_companies),
        "avoided_companies": list(prefs.avoided_companies),
    }


def preferences_from_json(data: Json) -> Preferences:
    d = default_preferences()
    pay = data.get("pay") or {}
    start = data.get("earliest_start_date")
    return Preferences(
        target_roles=tuple(data.get("target_roles", d.target_roles)),
        seniority_levels=tuple(data.get("seniority_levels", d.seniority_levels)),
        years_experience=_dec_from(data.get("years_experience")),
        key_skills=tuple(data.get("key_skills", d.key_skills)),
        preferred_locations=tuple(_place_from(p) for p in data.get("preferred_locations", [])),
        default_country=data.get("default_country", d.default_country),
        work_modes=frozenset(data.get("work_modes", d.work_modes)),
        willing_to_relocate=data.get("willing_to_relocate", d.willing_to_relocate),
        blocked_locations=tuple(_place_from(p) for p in data.get("blocked_locations", [])),
        job_types=frozenset(data.get("job_types", d.job_types)),
        pay=Pay(
            currency=pay.get("currency", d.pay.currency),
            min_annual=_dec_from(pay.get("min_annual")),
            target_annual=_dec_from(pay.get("target_annual")),
            basis=pay.get("basis", d.pay.basis),
        ),
        notice_period_days=data.get("notice_period_days", d.notice_period_days),
        earliest_start_date=date.fromisoformat(start) if start else None,
        preferred_companies=tuple(data.get("preferred_companies", d.preferred_companies)),
        avoided_companies=tuple(data.get("avoided_companies", d.avoided_companies)),
    )
