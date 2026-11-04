"""Documented defaults (FR-024) and the lakh-per-annum helpers (US2-AS5).

Nothing here is person-specific: a fresh install starts with the neutral values below.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from hiretitan.preferences.domain.model import Pay, Preferences

DEFAULT_COUNTRY: Final = "IN"
DEFAULT_CURRENCY: Final = "INR"
DEFAULT_NOTICE_DAYS: Final = 30
LAKH: Final = Decimal(100_000)

WORK_MODES: Final = ("onsite", "hybrid", "remote")
JOB_TYPES: Final = ("full_time", "contract", "internship")
SENIORITY_LEVELS: Final = (
    "intern",
    "entry",
    "junior",
    "mid",
    "senior",
    "lead",
    "staff",
    "principal",
    "manager",
    "director",
)
PAY_BASES: Final = ("fixed", "total")


def default_preferences() -> Preferences:
    return Preferences(
        default_country=DEFAULT_COUNTRY,
        work_modes=frozenset(WORK_MODES),
        job_types=frozenset({"full_time"}),
        pay=Pay(currency=DEFAULT_CURRENCY),
        notice_period_days=DEFAULT_NOTICE_DAYS,
    )


def lpa_to_annual(lpa: Decimal) -> Decimal:
    return lpa * LAKH


def annual_to_lpa(annual: Decimal) -> Decimal:
    return annual / LAKH
