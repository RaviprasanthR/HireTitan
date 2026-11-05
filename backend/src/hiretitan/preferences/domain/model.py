"""Preferences value types (data-model.md, ``Preferences``). Pure: no I/O, no frameworks.

Checks live in ``rules.py`` so every problem can be reported together, each with the path
of the field the UI should mark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Place:
    city: str | None
    country: str  # ISO 3166-1 alpha-2


@dataclass(frozen=True, slots=True)
class Pay:
    currency: str = "INR"  # ISO 4217
    min_annual: Decimal | None = None
    target_annual: Decimal | None = None
    basis: str = "fixed"  # fixed | total


@dataclass(frozen=True, slots=True)
class Preferences:
    target_roles: tuple[str, ...] = ()
    seniority_levels: tuple[str, ...] = ()
    years_experience: Decimal | None = None
    key_skills: tuple[str, ...] = ()
    preferred_locations: tuple[Place, ...] = ()
    default_country: str = "IN"
    work_modes: frozenset[str] = frozenset()
    willing_to_relocate: bool = False
    blocked_locations: tuple[Place, ...] = ()
    job_types: frozenset[str] = frozenset()
    pay: Pay = field(default_factory=Pay)
    notice_period_days: int | None = 30
    earliest_start_date: date | None = None
    preferred_companies: tuple[str, ...] = ()
    avoided_companies: tuple[str, ...] = ()
