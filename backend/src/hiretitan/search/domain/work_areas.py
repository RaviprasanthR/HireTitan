"""Areas of work and the title words that go with each (feature 002i, research R5). Pure."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hiretitan.search.domain.rules import AREAS_MAX, ITEM_TEXT_MAX
from hiretitan.search.domain.synonyms import normalize_phrase


@dataclass(frozen=True, slots=True)
class AreaEntry:
    """One area of work and the words that go with it."""

    name: str
    signals: tuple[str, ...]  # words in roles, titles and skills that suggest the person works here
    avoid_in_titles: tuple[str, ...]  # title words that mark a job as being in this area
    compatible: tuple[str, ...]  # areas that go with this one (their avoid words are not proposed)


WorkAreaTable = Mapping[str, AreaEntry]


# A signal in a role or a past title says more about the work than one in a skills list.
TITLE_WEIGHT = 3
SKILL_WEIGHT = 1
CLOSE_ENOUGH = 0.6  # an area scoring at least this share of the best one is kept as well


def _padded(text: str) -> str:
    return f" {normalize_phrase(text)} "


def _score(entry: AreaEntry, titles: Sequence[str], skills: Sequence[str]) -> int:
    signals = [normalize_phrase(s) for s in entry.signals]
    total = 0
    for texts, weight in ((titles, TITLE_WEIGHT), (skills, SKILL_WEIGHT)):
        for text in texts:
            padded = _padded(text)
            total += weight * sum(1 for signal in signals if f" {signal} " in padded)
    return total


def guess_areas(
    target_roles: Sequence[str],
    recent_titles: Sequence[str],
    skills: Sequence[str],
    table: WorkAreaTable,
) -> tuple[str, ...]:
    """The areas the person's roles, past titles and skills point to, best first.

    Whole-word matches only. Areas that score close to the best one are kept too (a person who
    works on both ends), up to the limit. Nothing is guessed when nothing matches.
    """
    titles = (*target_roles, *recent_titles)
    scores = {name: _score(entry, titles, skills) for name, entry in table.items()}
    scores = {name: score for name, score in scores.items() if score > 0 and name != "other"}
    if not scores:
        return ()
    best = max(scores.values())
    order = {name: index for index, name in enumerate(table)}
    chosen = sorted(
        (name for name, score in scores.items() if score >= CLOSE_ENOUGH * best),
        key=lambda name: (-scores[name], order[name]),
    )
    return tuple(chosen[:AREAS_MAX])


def avoid_with_area(areas: Sequence[str], table: WorkAreaTable) -> tuple[tuple[str, str], ...]:
    """``(word, area)``: title words that mark a job as being in an area the person's areas do not
    go with, and the area each word belongs to."""
    if not areas:
        return ()
    own = set(areas)
    for name in areas:
        if name in table:
            own.update(table[name].compatible)
    found: dict[str, str] = {}
    for name, entry in table.items():
        if name in own:
            continue
        for word in entry.avoid_in_titles:
            if len(word) <= ITEM_TEXT_MAX:
                found.setdefault(word, name)
    return tuple(found.items())


def avoid_words(areas: Sequence[str], table: WorkAreaTable) -> tuple[str, ...]:
    """Title words to avoid for a person in these areas (see ``avoid_with_area``)."""
    return tuple(word for word, _ in avoid_with_area(areas, table))
