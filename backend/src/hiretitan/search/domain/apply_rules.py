"""The free rules that skip obvious noise before any AI is asked (US1 AS3, AS4). Pure.

A missing fact never skips a job (FR-027): no place, no date and the rule does not apply.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from hiretitan.search.domain.places import city_aliases, key, same_city
from hiretitan.search.domain.rules import LocationRule, SearchRules
from hiretitan.search.domain.synonyms import expand


@dataclass(frozen=True, slots=True)
class RuleJob:
    title: str
    city: str | None
    country: str | None
    location_text: str | None
    posted_at: datetime | None


@dataclass(frozen=True, slots=True)
class Pass:
    pass


@dataclass(frozen=True, slots=True)
class Skip:
    rule_key: str  # title_words | title_avoid | blocked_locations | max_age_days
    reason: str


def _contains_phrase(text: str, phrase: str) -> bool:
    wanted = key(phrase)
    return bool(wanted) and f" {wanted} " in f" {key(text)} "


def _blocked(job: RuleJob, place: LocationRule) -> str | None:
    """The place as the person wrote it, if this job is there."""
    if place.city:
        if same_city(job.city, place.city):
            return place.city
        if job.city is None and job.location_text:
            text = f" {key(job.location_text)} "
            if any(f" {alias} " in text for alias in city_aliases(place.city)):
                return place.city
        return None
    if place.country and job.country and job.country.upper() == place.country.upper():
        return place.country
    return None


def apply(
    job: RuleJob,
    rules: SearchRules,
    now: datetime,
    synonyms: Mapping[str, tuple[str, ...]] | None = None,
) -> Pass | Skip:
    """The first rule that skips the job, else ``Pass``."""
    table = synonyms or {}
    if rules.title_words:
        phrases = {p for word in rules.title_words for p in expand(word.text, table)}
        if not any(_contains_phrase(job.title, p) for p in phrases):
            return Skip("title_words", "title matches none of your roles")
    for avoid in rules.title_avoid:
        if _contains_phrase(job.title, avoid.text):
            return Skip("title_avoid", f"title contains '{avoid.text}', a word you avoid")
    for place in rules.blocked_locations:
        if (named := _blocked(job, place)) is not None:
            return Skip("blocked_locations", f"location {named} is in your blocked list")
    if job.posted_at is not None and (now - job.posted_at).days > rules.max_age_days:
        return Skip("max_age_days", f"posted more than {rules.max_age_days} days ago")
    return Pass()
