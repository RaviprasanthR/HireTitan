"""The small cards the relevance check reads (FR-035, FR-035a). Pure.

A profile card holds only profile and preferences facts. A job card holds the posting fields
and a capped excerpt, so a long or hostile posting cannot flood the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Literal

from hiretitan.search.domain.tech_names import TechTable, is_technology

EXCERPT_MAX: Final = 1200
JOBS_PER_CALL_MAX: Final = 10
KEY_SKILLS_MAX: Final = 30
RECENT_TITLES_MAX: Final = 3

# whether the posting's own text was read: it was, a read failed, or none was tried (002i)
DescriptionStatus = Literal["read", "unreadable", "none"]

_SPACES = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ProfileCard:
    target_roles: tuple[str, ...]
    seniority: tuple[str, ...]
    years_experience: Decimal | None
    key_skills: tuple[str, ...]
    preferred_locations: tuple[str, ...]
    work_modes: tuple[str, ...]
    # 002i: the person's area of work and latest job titles; left out of the card when empty,
    # so older prompt versions see the card exactly as before
    areas: tuple[str, ...] = ()
    recent_titles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        card: dict[str, Any] = {
            "target_roles": list(self.target_roles),
            "seniority": list(self.seniority),
            "years_experience": None
            if self.years_experience is None
            else str(self.years_experience),
            "key_skills": list(self.key_skills[:KEY_SKILLS_MAX]),
            "preferred_locations": list(self.preferred_locations),
            "work_modes": list(self.work_modes),
        }
        if self.areas:
            card["areas"] = list(self.areas)
        if self.recent_titles:
            card["recent_titles"] = list(self.recent_titles[:RECENT_TITLES_MAX])
        return card


def main_skills(
    key_skills: tuple[str, ...] | list[str],
    profile_skills: tuple[str, ...] | list[str],
    table: TechTable,
) -> tuple[str, ...]:
    """The person's skills for the card: no repeats, languages and frameworks first, then tools.

    The order within each group is the order given (preferences first, then the profile).
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for skill in (*key_skills, *profile_skills):
        text = skill.strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            ordered.append(text)
    techs = [s for s in ordered if is_technology(s, table)]
    return tuple(techs + [s for s in ordered if s not in techs])


@dataclass(frozen=True, slots=True)
class JobCardInput:
    title: str
    company: str
    location: str | None
    work_mode: str | None
    skills_found: tuple[str, ...]
    years_found: Decimal | None
    description: str
    description_status: DescriptionStatus = "none"


def excerpt(description: str) -> str:
    return _SPACES.sub(" ", description).strip()[:EXCERPT_MAX]


def job_cards(jobs: list[JobCardInput]) -> tuple[list[dict[str, Any]], list[str]]:
    """The cards and their refs (``j1``, ``j2``...). Refs carry no database ids."""
    if not jobs:
        raise ValueError("Send at least one job.")
    if len(jobs) > JOBS_PER_CALL_MAX:
        raise ValueError(f"Send at most {JOBS_PER_CALL_MAX} jobs per call.")
    cards = [
        {
            "ref": f"j{index}",
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "work_mode": job.work_mode,
            "skills_found": list(job.skills_found),
            "years_found": None if job.years_found is None else str(job.years_found),
            "description_status": job.description_status,
            "excerpt": excerpt(job.description),
        }
        for index, job in enumerate(jobs, start=1)
    ]
    return cards, [f"j{index}" for index in range(1, len(cards) + 1)]
