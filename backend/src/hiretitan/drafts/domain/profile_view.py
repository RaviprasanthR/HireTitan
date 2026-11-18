"""What the drafts module needs to know of the confirmed profile. Pure.

The drafts module may not import the profile module, so ``hiretitan/drafts_wiring.py`` converts
the confirmed profile into these plain values. ``YearMonth`` is ``(year, month or None)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

YearMonth = tuple[int, int | None]
MONTHS: Final = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip


def format_ym(value: YearMonth | None) -> str:
    if value is None:
        return ""
    year, month = value
    return f"{MONTHS[month - 1]} {year}" if month else str(year)


@dataclass(frozen=True, slots=True)
class ContactView:
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperienceView:
    id: str
    employer: str
    title: str
    start: YearMonth | None = None
    end: YearMonth | None = None
    current: bool = False
    location: str | None = None
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EducationView:
    id: str
    institution: str
    qualification: str | None = None
    field_of_study: str | None = None
    start: YearMonth | None = None
    end: YearMonth | None = None


@dataclass(frozen=True, slots=True)
class ProjectView:
    id: str
    name: str
    description: str | None = None
    technologies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CertificationView:
    id: str
    name: str
    issuer: str | None = None
    date: YearMonth | None = None


@dataclass(frozen=True, slots=True)
class ProfileView:
    contact: ContactView
    headline: str | None = None
    summary: str | None = None
    experience: tuple[ExperienceView, ...] = ()
    education: tuple[EducationView, ...] = ()
    skills: tuple[str, ...] = ()
    projects: tuple[ProjectView, ...] = ()
    certifications: tuple[CertificationView, ...] = ()
