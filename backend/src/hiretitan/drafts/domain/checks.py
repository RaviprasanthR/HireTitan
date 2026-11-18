"""Truthfulness checks for drafted text (research R4, constitution IV). Pure.

The AI may only restate the person's own profile. Four rules, in code, not in a prompt:

1. numbers and years: every number must be in the profile facts (or the job's own title or
   company), and "N years" may not claim more than the profile shows;
2. technology terms must be in the facts, the job title or the company;
3. capitalised words in the middle of a sentence must be a known name (the job's company, the
   person's employers, schools, projects, certifications, technologies) or a plain greeting word;
4. cited fact ids must exist.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final

from hiretitan.drafts.domain.facts import Fact

PLACEHOLDER: Final = re.compile(r"\{[a-z_]+\}")
_NUMBER: Final = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(\+?)")
_YEARS_CLAIM: Final = re.compile(r"(\d+)\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
_WORD: Final = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")
_CAPITAL: Final = re.compile(r"\b[A-Z][A-Za-z0-9]+\b")
_SEGMENT: Final = re.compile(r"(?<=[.!?])\s+|\n+")
# Plain words that are capitalised in a greeting or a sign-off and say nothing about the person.
COMMON_CAPITALS: Final = frozenset(
    {
        "hi", "hello", "hey", "dear", "thanks", "thank", "best", "regards", "cheers", "kind",
        "warm", "sincerely", "linkedin", "english", "no", "yes", "if", "would", "could", "happy",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Problem:
    code: str
    message: str  # short, in plain words, so a repair turn can quote it


TechTerms = Sequence[tuple[str, tuple[str, ...]]]  # (name, aliases) of known technologies


def _numbers(text: str) -> set[str]:
    return {m.group(1).replace(",", "") for m in _NUMBER.finditer(text)}


def _words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(text)}


def _mentions(text: str, term: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


_USE_WORDS = (
    r"worked|work|working|experience|experienced|built|build|building|used|use|using|skilled|"
    r"proficient|expert|expertise|know|shipped|deployed|developed|developing|wrote|ran|running|"
    r"hands-on|background"
)


def _claims_use(text: str, term: str) -> bool:
    """Whether ``text`` says the person used ``term`` (a use word up to four words before it)."""
    pattern = rf"\b(?:{_USE_WORDS})\b(?:\W+\w+){{0,4}}?\W+" + re.escape(term) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def check_length(text: str, limit: int) -> list[Problem]:
    if len(text) > limit:
        return [Problem("too_long", f"The text is {len(text)} characters; the limit is {limit}.")]
    return []


def check_text(
    text: str,
    cited_ids: Collection[str],
    facts: Sequence[Fact],
    *,
    tech_terms: TechTerms,
    allowed_names: Collection[str],
    years: int | None,
    context: str = "",
) -> list[Problem]:
    """What is wrong with ``text`` as a statement about the person; empty when it is fine."""
    problems: list[Problem] = []
    body = PLACEHOLDER.sub(" ", text)
    fact_text = "\n".join(f.text for f in facts)
    known = fact_text + "\n" + context

    ids = {f.id for f in facts}
    for cited in cited_ids:
        if cited not in ids:
            problems.append(Problem("unknown_fact", f"Cited fact {cited!r} is not in the profile."))

    allowed_numbers = _numbers(known)
    claims = {m.start(1) for m in _YEARS_CLAIM.finditer(body)}
    for claim in _YEARS_CLAIM.finditer(body):
        n = int(claim.group(1))
        if years is None or n > years:
            problems.append(
                Problem("years", f"'{claim.group(0)}' is more experience than the profile shows.")
            )
    for match in _NUMBER.finditer(body):
        if match.start(1) in claims:
            continue
        number = match.group(1).replace(",", "")
        if number not in allowed_numbers:
            problems.append(Problem("number", f"The number {number} is not in the profile."))

    for name, aliases in tech_terms:
        for term in (name, *aliases):
            if not _mentions(body, term) or _mentions(fact_text, term):
                continue
            # a term only the job names may be mentioned, never claimed as the person's own
            if not _mentions(known, term) or _claims_use(body, term):
                problems.append(Problem("technology", f"{name} is not in the profile."))
                break

    allowed_words = _words(fact_text + " " + context + " " + " ".join(allowed_names))
    allowed_words |= COMMON_CAPITALS
    for name, aliases in tech_terms:
        allowed_words |= _words(" ".join((name, *aliases)))
    reported: set[str] = set()
    for segment in _SEGMENT.split(body):
        words = list(_CAPITAL.finditer(segment))
        for match in words:
            if match.start() == len(segment) - len(segment.lstrip()):
                continue  # the first word of a sentence is capitalised anyway
            word = match.group(0)
            if len(word) < 2 or word.casefold() in allowed_words or word in reported:
                continue
            if word.isupper():
                continue  # an acronym is judged as a technology term, above
            reported.add(word)
            problems.append(Problem("name", f"{word} is not a name the profile or job uses."))
    return problems
