"""Programming languages and frameworks named in job titles (feature 002i, research R6). Pure.

A job whose title names a technology, and none of the technologies it names are among the
person's skills, is not for them ("needs Java, which is not in your skills").
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from hiretitan.search.domain.synonyms import normalize_phrase

TechKind = Literal["language", "framework"]


@dataclass(frozen=True, slots=True)
class TechName:
    """One technology, how it may be written, and (for ordinary words like Go) where it counts."""

    name: str
    kind: TechKind
    aliases: tuple[str, ...]
    context: tuple[str, ...] = ()  # when set, the name counts only next to one of these words
    # the languages a framework is written in: a title naming Django is for a Python person too,
    # and a person with Spring has Java
    implies: tuple[str, ...] = ()


TechTable = tuple[TechName, ...]


def _forms(tech: TechName) -> set[str]:
    return {normalize_phrase(tech.name), *(normalize_phrase(a) for a in tech.aliases)}


def _candidates(tech: TechName) -> list[tuple[str, bool]]:
    """Every way to write the technology, with whether it needs a context word next to it."""
    forms = [(normalize_phrase(alias), False) for alias in tech.aliases]
    forms.append((normalize_phrase(tech.name), bool(tech.context)))
    return forms


# "Spring 2027", "Spring Internship": a season, not the framework
_SEASON = re.compile(r" ?(\d|intern|internship|cohort|batch)")


def _counts(text: str, phrase: str, tech: TechName, needs_context: bool) -> bool:
    if f" {phrase} " not in text:
        return False
    if not needs_context:
        return True
    if f" {phrase} to " in text:  # "Go to market" is not the language
        return False
    if _SEASON.match(text.split(f" {phrase} ", 1)[1]):
        return False
    return any(
        f" {phrase} {word} " in text or f" {word} {phrase} " in text for word in tech.context
    )


def names_in(title: str, table: TechTable) -> tuple[str, ...]:
    """The technologies a title names, in table order.

    The longest spelling is tried first and its words are used up, so "Node.js" is not also read
    as "JS" and "React Native" is not also read as something else.
    """
    text = f" {normalize_phrase(title)} "
    ranked = sorted(
        ((phrase, ctx, tech) for tech in table for phrase, ctx in _candidates(tech)),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    hit: set[str] = set()
    for phrase, needs_context, tech in ranked:
        if tech.name in hit or not _counts(text, phrase, tech, needs_context):
            continue
        hit.add(tech.name)
        text = text.replace(f" {phrase} ", f" {'~' * len(phrase)} ", 1)
    return tuple(tech.name for tech in table if tech.name in hit)


def _persons(skills: Sequence[str], table: TechTable) -> set[str]:
    """The table names the person has: a skill equal to a name or alias, or one that mentions it,
    and the languages those frameworks are written in."""
    have: set[str] = set()
    for skill in skills:
        wanted = normalize_phrase(skill)
        have.update(tech.name for tech in table if wanted in _forms(tech))
        have.update(names_in(skill, table))
    by_name = {tech.name: tech for tech in table}
    for name in list(have):
        have.update(by_name[name].implies)
    return have


def _list(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


def stack_skip_reason(title: str, skills: Sequence[str], table: TechTable) -> str | None:
    """Why the title's technology is not the person's, or None when the job may stay.

    Nothing is skipped when the title names no technology, when the person has any of the ones it
    names, or when nothing is known about the person's skills.
    """
    named = names_in(title, table)
    if not named or not skills:
        return None
    have = _persons(skills, table)
    if not have:
        return None  # none of the skills is a language or framework: nothing to compare
    by_name = {tech.name: tech for tech in table}
    if any(name in have or have & set(by_name[name].implies) for name in named):
        return None
    verb = "is" if len(named) == 1 else "are"
    return f"needs {_list(named)}, which {verb} not in your skills"


def is_technology(skill: str, table: TechTable) -> bool:
    """True when the skill is a language or framework in the table (or mentions one)."""
    wanted = normalize_phrase(skill)
    return any(wanted in _forms(tech) for tech in table) or bool(names_in(skill, table))
