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
        score = fuzz.token_set_ratio(title, key(other.title))
        if score >= TITLE_SIMILARITY_MIN:
            first, second = sorted((found.id, other.id))
            pairs.append(DuplicatePair(first, second, score))
    return sorted(pairs, key=lambda p: (p.first, p.second))
