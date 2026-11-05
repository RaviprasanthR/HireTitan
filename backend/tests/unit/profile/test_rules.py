"""T030: the rules a profile must pass to be confirmed (FR-018)."""

from __future__ import annotations

from typing import Any

from hiretitan.profile.domain.content import (
    Contact,
    Education,
    Experience,
    ProfileContent,
    YearMonth,
)
from hiretitan.profile.domain.rules import RuleError, confirm_errors


def profile(**kw: Any) -> ProfileContent:
    return ProfileContent(**{"contact": Contact(name="Jane Example"), "skills": ("Python",), **kw})


def paths(content: ProfileContent) -> list[str]:
    return [error.path for error in confirm_errors(content)]


def test_a_complete_profile_has_no_errors() -> None:
    job = Experience(
        employer="Acme", title="Engineer", start=YearMonth(2020, 1), end=YearMonth(2022, 6)
    )
    assert confirm_errors(profile(experience=(job,))) == []


def test_FR018_name_required() -> None:
    errors = confirm_errors(profile(contact=Contact(name="   ")))
    assert errors == [RuleError("contact.name", "Name is required")]


def test_FR018_needs_experience_education_or_skills() -> None:
    errors = confirm_errors(ProfileContent(contact=Contact(name="Jane")))
    assert [e.path for e in errors] == ["profile"]
    assert "experience, education or skills" in errors[0].message
    assert confirm_errors(ProfileContent(contact=Contact(name="Jane"), skills=("Go",))) == []
    edu = Education(institution="Example University")
    assert confirm_errors(ProfileContent(contact=Contact(name="Jane"), education=(edu,))) == []


def test_FR018_end_before_start_blocks() -> None:
    job = Experience(employer="A", title="T", start=YearMonth(2022, 5), end=YearMonth(2021, 1))
    uni = Education(institution="U", start=YearMonth(2019), end=YearMonth(2018))
    errors = confirm_errors(profile(experience=(job,), education=(uni,)))
    assert [e.path for e in errors] == ["experience[0].end", "education[0].end"]


def test_end_in_same_month_or_same_year_is_allowed() -> None:
    job = Experience(employer="A", title="T", start=YearMonth(2022, 5), end=YearMonth(2022, 5))
    uni = Education(institution="U", start=YearMonth(2019), end=YearMonth(2019, 3))
    assert confirm_errors(profile(experience=(job,), education=(uni,))) == []


def test_FR018_current_has_no_end() -> None:
    job = Experience(
        employer="A", title="T", start=YearMonth(2020), end=YearMonth(2021), current=True
    )
    assert paths(profile(experience=(job,))) == ["experience[0].end"]
    ongoing = Experience(employer="A", title="T", start=YearMonth(2020), current=True)
    assert confirm_errors(profile(experience=(ongoing,))) == []


def test_experience_needs_employer_and_title() -> None:
    blank = Experience(employer=" ", title="")
    assert paths(profile(experience=(blank,))) == ["experience[0].employer", "experience[0].title"]


def test_other_entries_need_their_name() -> None:
    from hiretitan.profile.domain.content import Certification, Project

    content = profile(
        education=(Education(institution=""),),
        projects=(Project(name=""),),
        certifications=(Certification(name=" "),),
        skills=("Python", "  "),
    )
    assert paths(content) == [
        "education[0].institution",
        "projects[0].name",
        "certifications[0].name",
        "skills[1]",
    ]


def test_edge_case_sparse_profile_allowed_with_name_and_skills() -> None:
    sparse = ProfileContent(contact=Contact(name="Fresh Grad"), skills=("Python", "SQL"))
    assert confirm_errors(sparse) == []


def test_errors_are_reported_together_not_one_at_a_time() -> None:
    errors = confirm_errors(ProfileContent(contact=Contact(name="")))
    assert {e.path for e in errors} == {"contact.name", "profile"}
