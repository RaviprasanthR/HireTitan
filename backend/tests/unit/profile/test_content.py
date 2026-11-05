"""T029: profile value types, with the bounds from data-model.md."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from hiretitan.profile.domain.content import (
    Certification,
    Contact,
    Education,
    Experience,
    Link,
    ProfileContent,
    Project,
    YearMonth,
    dedupe_skills,
)

JAN_2021 = YearMonth(2021, 1)


def exp(**kw: Any) -> Experience:
    return Experience(**{"employer": "Acme", "title": "Engineer", "start": JAN_2021, **kw})


def text(n: int) -> str:
    return "x" * n


def profile(**kw: Any) -> ProfileContent:
    return ProfileContent(contact=Contact(name="A"), **kw)


# (field, builder taking a size). The largest allowed size is accepted, one more is rejected.
BOUNDS: list[tuple[str, Callable[[int], object], int]] = [
    ("contact.name", lambda n: Contact(name=text(n)), 120),
    ("contact.location", lambda n: Contact(name="A", location=text(n)), 120),
    (
        "contact.links",
        lambda n: Contact(name="A", links=tuple(Link(url=f"u{i}") for i in range(n))),
        10,
    ),
    ("headline", lambda n: profile(headline=text(n)), 200),
    ("summary", lambda n: profile(summary=text(n)), 2000),
    ("experience", lambda n: profile(experience=tuple(exp() for _ in range(n))), 40),
    ("experience.employer", lambda n: exp(employer=text(n)), 200),
    ("experience.title", lambda n: exp(title=text(n)), 200),
    ("experience.bullets", lambda n: exp(bullets=tuple(text(5) for _ in range(n))), 30),
    ("experience.bullet", lambda n: exp(bullets=(text(n),)), 500),
    (
        "education",
        lambda n: profile(education=tuple(Education(institution="U") for _ in range(n))),
        20,
    ),
    ("education.institution", lambda n: Education(institution=text(n)), 200),
    ("education.grade", lambda n: Education(institution="U", grade=text(n)), 50),
    ("skills", lambda n: profile(skills=tuple(f"s{i}" for i in range(n))), 150),
    ("skill", lambda n: profile(skills=(text(n),)), 80),
    ("projects", lambda n: profile(projects=tuple(Project(name="P") for _ in range(n))), 30),
    ("project.name", lambda n: Project(name=text(n)), 200),
    ("project.description", lambda n: Project(name="P", description=text(n)), 1000),
    (
        "project.technologies",
        lambda n: Project(name="P", technologies=tuple(f"t{i}" for i in range(n))),
        30,
    ),
    (
        "certifications",
        lambda n: profile(certifications=tuple(Certification(name="C") for _ in range(n))),
        30,
    ),
    ("certification.name", lambda n: Certification(name=text(n)), 200),
]


@pytest.mark.parametrize(("field", "build", "limit"), BOUNDS, ids=[b[0] for b in BOUNDS])
def test_bounds_enforced(field: str, build: Callable[[int], object], limit: int) -> None:
    build(limit)
    with pytest.raises(ValueError, match=field.split(".")[-1]):
        build(limit + 1)


@pytest.mark.parametrize(
    "build",
    [
        lambda: YearMonth(1949, 1),
        lambda: YearMonth(2101, 1),
        lambda: YearMonth(2020, 0),
        lambda: YearMonth(2020, 13),
    ],
)
def test_year_month_ranges_enforced(build: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        build()


def test_incomplete_draft_is_representable() -> None:
    # Autosave stores incomplete drafts (FR-016); the confirm rules (T030) block them.
    draft = ProfileContent(
        contact=Contact(name=""), experience=(Experience(employer="", title=""),)
    )
    assert draft.contact.name == ""


def test_year_month_ordering_and_optional_month() -> None:
    assert YearMonth(2020, 5) < YearMonth(2021, 1)
    assert YearMonth(2020) <= YearMonth(2020, 1)
    assert YearMonth(2020, None).month is None


def test_items_get_stable_distinct_ids() -> None:
    a, b = exp(), exp()
    assert a.id != b.id


def test_edge_case_skills_dedup_case_and_space_only() -> None:
    skills = ["Python", "python", "  PYTHON ", "Machine  Learning", "machine learning"]
    assert dedupe_skills(skills) == ("Python", "Machine  Learning")
    assert profile(skills=("SQL", "sql", "Postgres")).skills == ("SQL", "Postgres")


def test_clarification_Q4_no_synonym_merge() -> None:
    assert dedupe_skills(["ReactJS", "React", "React.js"]) == ("ReactJS", "React", "React.js")
