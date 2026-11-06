"""Propose the first search rules from what the person already told the app (US2, FR-001).

Pure and deterministic: no AI, no I/O (research R9). The caller reads the confirmed profile and
the saved preferences and hands over plain values, so this module never imports another feature.
Every proposed item records where it came from, and the person edits and approves the result.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from hiretitan.search.domain.rules import (
    BLOCKED_LOCATIONS_MAX,
    DEFAULT_MAX_AGE_DAYS,
    ITEM_TEXT_MAX,
    PREFERRED_LOCATIONS_MAX,
    STACK_KEYWORDS_MAX,
    TITLE_WORDS_MAX,
    LocationRule,
    RuleItem,
    SearchRules,
)
from hiretitan.search.domain.synonyms import expand, normalize_phrase


@dataclass(frozen=True, slots=True)
class PlaceInput:
    city: str | None
    country: str | None


@dataclass(frozen=True, slots=True)
class ProposalInput:
    target_roles: tuple[str, ...] = ()
    seniority_levels: tuple[str, ...] = ()
    years_experience: Decimal | None = None
    key_skills: tuple[str, ...] = ()
    # every skill the profile mentions, repeats included (skills list, project technologies...);
    # how often a skill appears decides its order
    profile_skills: tuple[str, ...] = ()
    preferred_locations: tuple[PlaceInput, ...] = ()
    blocked_locations: tuple[PlaceInput, ...] = ()
    work_modes: frozenset[str] = frozenset()


def propose_rules(source: ProposalInput, synonyms: Mapping[str, tuple[str, ...]]) -> SearchRules:
    return SearchRules(
        title_words=_title_words(source.target_roles, synonyms),
        title_avoid=(),  # FR-005: only the person adds avoid words
        blocked_locations=_places(
            source.blocked_locations, "blocked_locations", BLOCKED_LOCATIONS_MAX
        ),
        max_age_days=DEFAULT_MAX_AGE_DAYS,
        stack_keywords=_stack_keywords(source.key_skills, source.profile_skills),
        preferred_locations=_places(
            source.preferred_locations, "preferred_locations", PREFERRED_LOCATIONS_MAX
        ),
        work_modes=source.work_modes,
        seniority=source.seniority_levels,
        years_experience=source.years_experience,
    )


def _title_words(
    roles: tuple[str, ...], synonyms: Mapping[str, tuple[str, ...]]
) -> tuple[RuleItem, ...]:
    items: list[RuleItem] = []
    seen: set[str] = set()
    for index, role in enumerate(roles):
        text = role.strip()
        key = normalize_phrase(text)
        if text and len(text) <= ITEM_TEXT_MAX and key not in seen:
            seen.add(key)
            items.append(RuleItem(text, f"preference:target_roles[{index}]"))
    items = items[:TITLE_WORDS_MAX]
    seen = {normalize_phrase(i.text) for i in items}
    for role in roles:
        for phrase in expand(role, synonyms)[1:]:
            if phrase not in seen and len(phrase) <= ITEM_TEXT_MAX:
                seen.add(phrase)
                items.append(RuleItem(phrase, "synonym_table"))
    return tuple(items[:TITLE_WORDS_MAX])


def _stack_keywords(
    key_skills: tuple[str, ...], profile_skills: tuple[str, ...]
) -> tuple[RuleItem, ...]:
    items: list[RuleItem] = []
    seen: set[str] = set()
    for index, skill in enumerate(key_skills):
        text = skill.strip()
        key = text.lower()
        if text and len(text) <= ITEM_TEXT_MAX and key not in seen:
            seen.add(key)
            items.append(RuleItem(text, f"preference:key_skills[{index}]"))
    cleaned = [s.strip() for s in profile_skills if s.strip() and len(s.strip()) <= ITEM_TEXT_MAX]
    counts = Counter(s.lower() for s in cleaned)
    first_seen: dict[str, str] = {}
    for skill in cleaned:
        first_seen.setdefault(skill.lower(), skill)
    # most frequent first; ties keep the order the profile lists them (dicts keep insertion order)
    for key in sorted(first_seen, key=lambda k: -counts[k]):
        if key not in seen:
            seen.add(key)
            items.append(RuleItem(first_seen[key], "profile:skills"))
    return tuple(items[:STACK_KEYWORDS_MAX])


def _places(places: tuple[PlaceInput, ...], name: str, maximum: int) -> tuple[LocationRule, ...]:
    return tuple(
        LocationRule(place.city, place.country, f"preference:{name}[{index}]")
        for index, place in enumerate(places)
        if place.city or place.country
    )[:maximum]
