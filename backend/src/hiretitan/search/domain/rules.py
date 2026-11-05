"""Search rules: what the person's roles, skills and places mean for a search (FR-001, FR-005).

Pure data and validation. Every item says where it came from (``origin``) so the person can see
why a rule exists. Each rule kind has an ``effect``: ``skips`` rules remove a job without any AI,
``guides_ai`` rules only describe the person to the relevance check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, Literal

Effect = Literal["skips", "guides_ai"]

EFFECTS: Final[dict[str, Effect]] = {
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

WORK_MODES: Final = frozenset({"onsite", "hybrid", "remote"})
DEFAULT_MAX_AGE_DAYS: Final = 30

TITLE_WORDS_MAX: Final = 30
TITLE_AVOID_MAX: Final = 30
BLOCKED_LOCATIONS_MAX: Final = 30
STACK_KEYWORDS_MAX: Final = 50
PREFERRED_LOCATIONS_MAX: Final = 30
ITEM_TEXT_MAX: Final = 60
MAX_AGE_RANGE: Final = (1, 365)
YEARS_RANGE: Final = (Decimal(0), Decimal(50))

_ORIGIN = re.compile(r"(preference|profile):[a-z_]+(\[\d+\])?|synonym_table|user")


@dataclass(frozen=True, slots=True)
class RuleItem:
    text: str
    origin: str  # preference:<field> | profile:<field> | synonym_table | user


@dataclass(frozen=True, slots=True)
class LocationRule:
    city: str | None
    country: str | None
    origin: str


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    message: str


class RulesInvalidError(ValueError):
    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__("; ".join(f"{e.field}: {e.message}" for e in errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class SearchRules:
    title_words: tuple[RuleItem, ...] = ()
    title_avoid: tuple[RuleItem, ...] = ()
    blocked_locations: tuple[LocationRule, ...] = ()
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
    stack_keywords: tuple[RuleItem, ...] = ()
    preferred_locations: tuple[LocationRule, ...] = ()
    work_modes: frozenset[str] = field(default_factory=frozenset)
    seniority: tuple[str, ...] = ()
    years_experience: Decimal | None = None

    def validate(self) -> None:
        """Raise ``RulesInvalidError`` listing every problem, so the page can show them all."""
        errors: list[FieldError] = []
        _check_words(errors, "title_words", self.title_words, TITLE_WORDS_MAX, minimum=1)
        _check_words(errors, "title_avoid", self.title_avoid, TITLE_AVOID_MAX)
        _check_words(errors, "stack_keywords", self.stack_keywords, STACK_KEYWORDS_MAX)
        _check_places(errors, "blocked_locations", self.blocked_locations, BLOCKED_LOCATIONS_MAX)
        _check_places(
            errors, "preferred_locations", self.preferred_locations, PREFERRED_LOCATIONS_MAX
        )
        low, high = MAX_AGE_RANGE
        if not low <= self.max_age_days <= high:
            errors.append(FieldError("max_age_days", f"Use a number from {low} to {high}."))
        if not self.work_modes <= WORK_MODES:
            errors.append(FieldError("work_modes", "Use onsite, hybrid or remote."))
        if self.years_experience is not None and not (
            YEARS_RANGE[0] <= self.years_experience <= YEARS_RANGE[1]
        ):
            errors.append(FieldError("years_experience", "Use a number from 0 to 50."))
        if errors:
            raise RulesInvalidError(errors)


def _check_words(
    errors: list[FieldError],
    name: str,
    items: tuple[RuleItem, ...],
    maximum: int,
    *,
    minimum: int = 0,
) -> None:
    if len(items) < minimum:
        errors.append(FieldError(name, f"Add at least {minimum}."))
    if len(items) > maximum:
        errors.append(FieldError(name, f"At most {maximum} items."))
    for item in items:
        if not item.text.strip() or len(item.text) > ITEM_TEXT_MAX:
            errors.append(FieldError(name, f"Each item is 1 to {ITEM_TEXT_MAX} characters."))
            break
    if any(not _ORIGIN.fullmatch(item.origin) for item in items):
        errors.append(FieldError(name, "An item has an unknown origin."))


def _check_places(
    errors: list[FieldError], name: str, items: tuple[LocationRule, ...], maximum: int
) -> None:
    if len(items) > maximum:
        errors.append(FieldError(name, f"At most {maximum} items."))
    if any(not (place.city or place.country) for place in items):
        errors.append(FieldError(name, "Each place needs a city or a country."))
    if any(not _ORIGIN.fullmatch(place.origin) for place in items):
        errors.append(FieldError(name, "An item has an unknown origin."))
