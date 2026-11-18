"""The facts a draft may use, taken from the confirmed profile (research R4). Pure.

A fact is one line of the person's own profile with a stable id. The AI is shown facts and asked
to cite ids; the checks compare what it wrote against these lines. The person's name and contact
details are never facts (constitution, contacts privacy).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from hiretitan.drafts.domain.profile_view import ProfileView, YearMonth

FactKind = Literal["bullet", "skill", "project", "certification", "summary"]
MAX_FACTS: Final = 80


@dataclass(frozen=True, slots=True)
class Fact:
    id: str
    kind: FactKind
    text: str


def _skill_id(skill: str) -> str:
    return "skill:" + " ".join(skill.split()).casefold()


def drafting_facts(profile: ProfileView) -> tuple[Fact, ...]:
    """Every usable line of the profile, in a fixed order, with ids that do not change."""
    facts: list[Fact] = []
    if profile.summary and profile.summary.strip():
        facts.append(Fact("summary", "summary", profile.summary.strip()))
    elif profile.headline and profile.headline.strip():
        facts.append(Fact("summary", "summary", profile.headline.strip()))
    for job in profile.experience:
        facts.append(Fact(f"{job.id}:role", "bullet", f"{job.title} at {job.employer}"))
        for index, bullet in enumerate(job.bullets):
            if bullet.strip():
                facts.append(Fact(f"{job.id}:{index}", "bullet", bullet.strip()))
    for skill in profile.skills:
        facts.append(Fact(_skill_id(skill), "skill", skill))
    for project in profile.projects:
        parts = [project.name, project.description or "", ", ".join(project.technologies)]
        facts.append(Fact(f"project:{project.id}", "project", ". ".join(p for p in parts if p)))
    for cert in profile.certifications:
        text = f"{cert.name} ({cert.issuer})" if cert.issuer else cert.name
        facts.append(Fact(f"cert:{cert.id}", "certification", text))
    return tuple(facts)


def _month_index(value: YearMonth, *, end: bool) -> int:
    year, month_value = value
    month = month_value if month_value is not None else (12 if end else 1)
    return year * 12 + month - 1


def years_of_experience(profile: ProfileView, today: date) -> int | None:
    """Whole years of work, overlapping jobs counted once; None when no job has a start date."""
    spans: list[tuple[int, int]] = []
    now = today.year * 12 + today.month - 1
    for job in profile.experience:
        if job.start is None:
            continue
        start = _month_index(job.start, end=False)
        end = now if (job.current or job.end is None) else _month_index(job.end, end=True)
        if end >= start:
            spans.append((start, end + 1))
    if not spans:
        return None
    spans.sort()
    months = 0
    cur_start, cur_end = spans[0]
    for start, end in spans[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            months += cur_end - cur_start
            cur_start, cur_end = start, end
    months += cur_end - cur_start
    return months // 12
