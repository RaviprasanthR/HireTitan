"""T032: which fields differ between the current profile and a new extraction (FR-014)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from hiretitan.profile.domain.content import (
    Certification,
    Contact,
    Education,
    Experience,
    ProfileContent,
    Project,
    YearMonth,
)
from hiretitan.profile.domain.diff import changed_paths


def base(**kw: Any) -> ProfileContent:
    return ProfileContent(
        **{
            "contact": Contact(name="Jane Example", location="Pune"),
            "headline": "Backend engineer",
            "experience": (
                Experience(
                    employer="Acme", title="Engineer", start=YearMonth(2020), bullets=("Built X",)
                ),
            ),
            "education": (Education(institution="Example University", qualification="BSc"),),
            "skills": ("Python", "SQL"),
            "projects": (Project(name="Tool", description="A tool"),),
            "certifications": (Certification(name="Cert A"),),
            **kw,
        }
    )


def test_FR014_identical_profile_no_changes() -> None:
    again = replace(base())  # same values, but a re-extraction mints fresh item ids
    fresh_ids = base()
    assert changed_paths(base(), again) == []
    assert changed_paths(fresh_ids, base()) == []


def test_FR014_changed_fields_marked() -> None:
    current = base()
    job = replace(current.experience[0], title="Senior Engineer")
    new = replace(
        current,
        contact=replace(current.contact, name="Jane E. Example"),
        headline="Platform engineer",
        experience=(job,),
        skills=("Python", "Go"),
    )
    assert changed_paths(current, new) == [
        "contact.name",
        "headline",
        "experience[Acme | Engineer].title",
        "skills",
    ]


def test_experience_bullets_and_dates_are_compared() -> None:
    current = base()
    job = replace(current.experience[0], bullets=("Built Y",), start=YearMonth(2019))
    new = replace(current, experience=(job,))
    assert changed_paths(current, new) == [
        "experience[Acme | Engineer].start",
        "experience[Acme | Engineer].bullets",
    ]


def test_FR014_added_and_removed_entries() -> None:
    current = base()
    new = replace(
        current,
        experience=(Experience(employer="Globex", title="Developer"),),
        education=(),
        projects=(*current.projects, Project(name="Second")),
        certifications=(),
    )
    assert changed_paths(current, new) == [
        "experience[Acme | Engineer]",
        "experience[Globex | Developer]",
        "education[Example University | BSc]",
        "projects[Second]",
        "certifications[Cert A]",
    ]


def test_matching_ignores_case_and_spacing() -> None:
    current = base()
    job = replace(current.experience[0], employer="  ACME ", title="engineer")
    assert changed_paths(current, replace(current, experience=(job,))) == []


def test_skills_compare_as_a_set_ignoring_order_and_case() -> None:
    current = base()
    assert changed_paths(current, replace(current, skills=("sql", "PYTHON"))) == []
    assert changed_paths(current, replace(current, skills=("Python",))) == ["skills"]
