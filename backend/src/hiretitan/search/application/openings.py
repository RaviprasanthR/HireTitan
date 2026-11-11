"""Open-role counts per company, derived from the Explore list (feature 002b, US3, FR-017).

Nothing is stored: the counts are computed from the titles of the jobs on the Explore list, so
they cannot drift from it (SC-005). A company that has never been searched has no count at all
(``None``, shown as "not searched yet"), which is not the same as zero (FR-019).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Final, Protocol
from uuid import UUID

from hiretitan.search.domain.job_area import Area, areas_of

AREAS: Final[tuple[Area, ...]] = ("frontend", "backend", "qa")


class OpeningsStore(Protocol):
    async def explore_titles(self) -> list[tuple[UUID, bool, str | None]]:
        """``(company_id, searched, title)`` for every company, one row per Explore job.

        A company with no Explore job appears once with a ``None`` title.
        """
        ...

    async def explore_jobs(self, company_id: UUID) -> Sequence[Any]:
        """The company's Explore jobs, newest first."""
        ...


async def openings_by_company(store: OpeningsStore) -> dict[UUID, dict[str, int] | None]:
    searched: dict[UUID, bool] = {}
    counts: dict[UUID, dict[str, int]] = defaultdict(lambda: dict.fromkeys(AREAS, 0))
    for company_id, was_searched, title in await store.explore_titles():
        searched[company_id] = was_searched
        counts[company_id]  # make sure a company with no jobs still gets its zeros
        for area in areas_of(title) if title else ():
            counts[company_id][area] += 1
    return {cid: counts[cid] if searched[cid] else None for cid in searched}


async def jobs_for_area(store: OpeningsStore, company_id: UUID, area: Area) -> list[Any]:
    """The company's Explore jobs that count in ``area``: the rows behind one count."""
    return [row for row in await store.explore_jobs(company_id) if area in areas_of(row.title)]
