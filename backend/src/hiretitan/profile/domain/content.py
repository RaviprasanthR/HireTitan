"""Profile value types (data-model.md, ``ProfileContent``). Pure: no I/O, no frameworks.

Every type enforces its upper bounds on construction and raises ``ValueError`` naming the
field, so an oversized profile cannot exist. Required fields (name, employer, title...) are
*not* enforced here: an autosaved draft may be incomplete (FR-016). The confirm rules in
``rules.py`` block an incomplete profile from becoming a version (FR-018).
Strings are kept exactly as given: the user's wording is never rewritten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID, uuid4

MAX_LINKS = 10
MAX_EXPERIENCE, MAX_EDUCATION, MAX_PROJECTS, MAX_CERTIFICATIONS = 40, 20, 30, 30
MAX_BULLETS, MAX_BULLET = 30, 500
MAX_SKILLS, MAX_SKILL = 150, 80
MAX_TECHNOLOGIES = 30


def _text(name: str, value: str | None, maximum: int) -> None:
    if value is not None and len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")


def _count(name: str, items: tuple[object, ...], maximum: int) -> None:
    if len(items) > maximum:
        raise ValueError(f"{name} must have at most {maximum} entries")


@dataclass(frozen=True, slots=True)
class YearMonth:
    year: int
    month: int | None = None

    def __post_init__(self) -> None:
        if not 1950 <= self.year <= 2100:
            raise ValueError("year must be between 1950 and 2100")
        if self.month is not None and not 1 <= self.month <= 12:
            raise ValueError("month must be between 1 and 12")

    def _key(self) -> tuple[int, int]:
        return (self.year, self.month or 1)

    def __lt__(self, other: YearMonth) -> bool:
        return self._key() < other._key()

    def __le__(self, other: YearMonth) -> bool:
        return self._key() <= other._key()


@dataclass(frozen=True, slots=True)
class Link:
    url: str
    label: str | None = None

    def __post_init__(self) -> None:
        _text("link url", self.url, 500)
        _text("link label", self.label, 100)


@dataclass(frozen=True, slots=True)
class Contact:
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: tuple[Link, ...] = ()

    def __post_init__(self) -> None:
        _text("contact name", self.name, 120)
        _text("contact location", self.location, 120)
        _count("contact links", self.links, MAX_LINKS)


@dataclass(frozen=True, slots=True)
class Experience:
    employer: str
    title: str
    start: YearMonth | None = None
    end: YearMonth | None = None
    current: bool = False
    location: str | None = None
    bullets: tuple[str, ...] = ()
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _text("experience employer", self.employer, 200)
        _text("experience title", self.title, 200)
        _text("experience location", self.location, 120)
        _count("experience bullets", self.bullets, MAX_BULLETS)
        for bullet in self.bullets:
            _text("experience bullet", bullet, MAX_BULLET)


@dataclass(frozen=True, slots=True)
class Education:
    institution: str
    qualification: str | None = None
    field_of_study: str | None = None
    start: YearMonth | None = None
    end: YearMonth | None = None
    grade: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _text("education institution", self.institution, 200)
        _text("education qualification", self.qualification, 200)
        _text("education field", self.field_of_study, 200)
        _text("education grade", self.grade, 50)


@dataclass(frozen=True, slots=True)
class Project:
    name: str
    description: str | None = None
    technologies: tuple[str, ...] = ()
    link: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _text("project name", self.name, 200)
        _text("project description", self.description, 1000)
        _count("project technologies", self.technologies, MAX_TECHNOLOGIES)
        _text("project link", self.link, 500)


@dataclass(frozen=True, slots=True)
class Certification:
    name: str
    issuer: str | None = None
    date: YearMonth | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _text("certification name", self.name, 200)
        _text("certification issuer", self.issuer, 200)


_SPACES = re.compile(r"\s+")


def skill_key(skill: str) -> str:
    """The comparison key for skills: case- and space-insensitive, nothing smarter."""
    return _SPACES.sub(" ", skill).strip().casefold()


def dedupe_skills(skills: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Unique case- and space-insensitively; the first wording wins. No synonym merging."""
    seen: set[str] = set()
    kept: list[str] = []
    for skill in skills:
        key = skill_key(skill)
        if key in seen:
            continue
        seen.add(key)
        kept.append(skill)
    return tuple(kept)


@dataclass(frozen=True, slots=True)
class ProfileContent:
    contact: Contact
    headline: str | None = None
    summary: str | None = None
    experience: tuple[Experience, ...] = ()
    education: tuple[Education, ...] = ()
    skills: tuple[str, ...] = ()
    projects: tuple[Project, ...] = ()
    certifications: tuple[Certification, ...] = ()

    def __post_init__(self) -> None:
        _text("headline", self.headline, 200)
        _text("summary", self.summary, 2000)
        _count("experience", self.experience, MAX_EXPERIENCE)
        _count("education", self.education, MAX_EDUCATION)
        _count("projects", self.projects, MAX_PROJECTS)
        _count("certifications", self.certifications, MAX_CERTIFICATIONS)
        for skill in self.skills:
            _text("skill", skill, MAX_SKILL)
        object.__setattr__(self, "skills", dedupe_skills(self.skills))
        _count("skills", self.skills, MAX_SKILLS)
