"""SearchRules to and from the JSON stored in ``search_rule_sets.rules`` (pure)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from hiretitan.search.domain.rules import (
    DEFAULT_MAX_AGE_DAYS,
    FieldError,
    LocationRule,
    RuleItem,
    RulesInvalidError,
    SearchRules,
)


def rules_to_dict(rules: SearchRules) -> dict[str, Any]:
    years = rules.years_experience
    return {
        "title_words": [_item(i) for i in rules.title_words],
        "title_avoid": [_item(i) for i in rules.title_avoid],
        "blocked_locations": [_place(p) for p in rules.blocked_locations],
        "max_age_days": rules.max_age_days,
        "stack_keywords": [_item(i) for i in rules.stack_keywords],
        "preferred_locations": [_place(p) for p in rules.preferred_locations],
        "work_modes": sorted(rules.work_modes),
        "seniority": list(rules.seniority),
        "years_experience": None if years is None else str(years),
    }


def rules_from_dict(data: dict[str, Any]) -> SearchRules:
    """Read stored or submitted JSON. Anything malformed raises ``RulesInvalidError``."""
    try:
        years = data.get("years_experience")
        return SearchRules(
            title_words=_items(data, "title_words"),
            title_avoid=_items(data, "title_avoid"),
            blocked_locations=_places(data, "blocked_locations"),
            max_age_days=int(data.get("max_age_days", DEFAULT_MAX_AGE_DAYS)),
            stack_keywords=_items(data, "stack_keywords"),
            preferred_locations=_places(data, "preferred_locations"),
            work_modes=frozenset(str(m) for m in data.get("work_modes", [])),
            seniority=tuple(str(s) for s in data.get("seniority", [])),
            years_experience=None if years is None else Decimal(str(years)),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError) as error:
        raise RulesInvalidError(
            [FieldError("rules", "The rules are not in the expected shape.")]
        ) from error


def _item(item: RuleItem) -> dict[str, str]:
    return {"text": item.text, "origin": item.origin}


def _place(place: LocationRule) -> dict[str, Any]:
    return {"city": place.city, "country": place.country, "origin": place.origin}


def _items(data: dict[str, Any], name: str) -> tuple[RuleItem, ...]:
    return tuple(RuleItem(str(i["text"]), str(i.get("origin", "user"))) for i in data.get(name, []))


def _places(data: dict[str, Any], name: str) -> tuple[LocationRule, ...]:
    return tuple(
        LocationRule(i.get("city"), i.get("country"), str(i.get("origin", "user")))
        for i in data.get(name, [])
    )
