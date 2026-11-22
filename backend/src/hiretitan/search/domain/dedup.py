"""Finding the same job twice (research R8, FR-020, FR-021). Pure.

Only exact keys merge: the same canonical link, or the same requisition on the same board
provider. A similar title at the same company and city is a *candidate*; the person decides.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from rapidfuzz import fuzz

from hiretitan.search.domain.places import key, same_city

TITLE_SIMILARITY_MIN: Final = 92
# Stricter than a candidate: a title that differs by a word (a level, a team) is another job.
SAME_POSTING_TITLE_MIN: Final = 95
# The shorter title must have at least two thirds as many words as the longer: "Backend Engineer"
# and "Backend Engineer (Python)" are candidates, "Program Manager II" and "Program Manager II,
# Global Catalog Operations" are two postings (a word-set score alone calls them identical).
TITLE_WORDS_RATIO_MIN: Final = 2 / 3


@dataclass(frozen=True, slots=True)
class DedupJob:
    id: UUID
    company_name: str
    city: str | None
    title: str
    canonical_url: str | None
    ats_vendor: str | None
    requisition_id: str | None


@dataclass(frozen=True, slots=True)
class DuplicatePair:
    """Two jobs that may be the same; ``first`` is the lower id."""

    first: UUID
    second: UUID
    similarity: float


def exact_match(found: DedupJob, existing: Iterable[DedupJob]) -> UUID | None:
    for other in existing:
        if other.id == found.id:
            continue
        if found.canonical_url and found.canonical_url == other.canonical_url:
            return other.id
        if (
            found.ats_vendor
            and found.requisition_id
            and (found.ats_vendor, found.requisition_id) == (other.ats_vendor, other.requisition_id)
        ):
            return other.id
    return None


def fuzzy_candidates(found: DedupJob, existing: Iterable[DedupJob]) -> list[DuplicatePair]:
    """Same company, same known city and a very similar title. Never merges anything."""
    company = key(found.company_name)
    title = key(found.title)
    pairs: list[DuplicatePair] = []
    for other in existing:
        if other.id == found.id or key(other.company_name) != company:
            continue
        if not same_city(found.city, other.city):
            continue
        if exact_match(found, [other]) is not None:
            continue
        other_title = key(other.title)
        if not _close_in_size(title, other_title):
            continue
        score = fuzz.token_set_ratio(title, other_title)
        if score >= TITLE_SIMILARITY_MIN:
            first, second = sorted((found.id, other.id))
            pairs.append(DuplicatePair(first, second, score))
    return sorted(pairs, key=lambda p: (p.first, p.second))


def _close_in_size(a: str, b: str) -> bool:
    words_a, words_b = len(a.split()), len(b.split())
    if not words_a or not words_b:
        return False
    return min(words_a, words_b) / max(words_a, words_b) >= TITLE_WORDS_RATIO_MIN


def same_posting_again(found: DedupJob, other: DedupJob) -> bool:
    """True when ``found`` is almost certainly the posting ``other`` already is: the same company,
    the same known city and a title that is the same but for punctuation or a letter. Used only to
    keep a job already in the pipeline from being listed a second time under another link."""
    if key(found.company_name) != key(other.company_name) or not same_city(found.city, other.city):
        return False
    return fuzz.ratio(key(found.title), key(other.title)) >= SAME_POSTING_TITLE_MIN
