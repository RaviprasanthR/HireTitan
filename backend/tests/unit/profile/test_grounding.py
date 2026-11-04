"""T031: the grounding check drops anything the resume does not support (FR-011, SC-004)."""

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
from hiretitan.profile.domain.grounding import GroundingResult, ground, normalize

SOURCE = """
Jane Example
Pune, India

SUMMARY
Backend engineer with six years of experience building data pipelines and APIs.

EXPERIENCE
Acme Corp - Senior Software Engineer          Jan 2021 - Present
• Cut nightly batch time by 40% by rewriting the ingestion service in Go and
  moving it to a queue-based design for 12 regional teams
• Led a team of 5 engineers on the billing platform migration
Globex Ltd - Software Engineer                06/2017 - 12/2020
• Built REST APIs in Python serving 2M requests per day

EDUCATION
Example Institute of Technology - B.Tech Computer Science, 2013 - 2017

SKILLS
Python, Go, PostgreSQL, C++, Node.js, CI/CD

PROJECTS
Tracer - an open source request tracing tool written in Rust

CERTIFICATIONS
AWS Certified Developer, 2022
"""


def profile(**kw: Any) -> ProfileContent:
    return ProfileContent(**{"contact": Contact(name="Jane Example"), **kw})


def run(content: ProfileContent) -> GroundingResult:
    return ground(content, SOURCE)


def dropped_paths(result: GroundingResult) -> list[str]:
    return [d.path for d in result.dropped]


def test_normalize_keeps_plus_hash_dot_and_folds_the_rest() -> None:
    assert normalize("  C++ / C#,  Node.js  ") == "c++ c# node.js"  # noqa: RUF001
    assert normalize("ＰＹＴＨＯＮ") == "python"  # noqa: RUF001 - NFKC, casefold


def test_a_fully_supported_profile_is_kept_untouched() -> None:
    job = Experience(
        employer="Acme Corp",
        title="Senior Software Engineer",
        start=YearMonth(2021, 1),
        current=True,
        bullets=("Led a team of 5 engineers on the billing platform migration",),
    )
    content = profile(
        experience=(job,),
        skills=("Python", "Go", "PostgreSQL", "C++", "Node.js"),
        education=(
            Education(institution="Example Institute of Technology", qualification="B.Tech"),
        ),
        certifications=(Certification(name="AWS Certified Developer", date=YearMonth(2022)),),
        projects=(Project(name="Tracer"),),
        summary="Backend engineer with six years of experience building data pipelines and APIs.",
    )
    result = run(content)
    assert result.dropped == []
    assert result.profile == content


def test_FR011_planted_skill_dropped() -> None:
    result = run(profile(skills=("Python", "Kubernetes", "Rust")))
    assert result.profile.skills == ("Python", "Rust")
    assert [(d.path, d.value) for d in result.dropped] == [("skills[1]", "Kubernetes")]
    assert result.dropped[0].reason == "not found in your resume"


def test_FR011_planted_employer_dropped() -> None:
    fake = Experience(employer="Initech", title="Software Engineer")
    real = Experience(employer="Globex Ltd", title="Software Engineer")
    result = run(profile(experience=(fake, real)))
    assert [e.employer for e in result.profile.experience] == ["Globex Ltd"]
    assert dropped_paths(result) == ["experience[0]"]


def test_planted_title_drops_the_entry() -> None:
    wrong = Experience(employer="Acme Corp", title="Chief Technology Officer")
    result = run(profile(experience=(wrong,)))
    assert result.profile.experience == ()


def test_FR011_changed_number_in_bullet_dropped() -> None:
    bullets = (
        "Cut nightly batch time by 90% by rewriting the ingestion service in Go",
        "Led a team of 5 engineers on the billing platform migration",
    )
    job = Experience(employer="Acme Corp", title="Senior Software Engineer", bullets=bullets)
    result = run(profile(experience=(job,)))
    assert result.profile.experience[0].bullets == (bullets[1],)
    assert dropped_paths(result) == ["experience[0].bullets[0]"]


def test_FR011_wrapped_bullet_kept() -> None:
    # In the source this bullet is wrapped over two lines.
    bullet = (
        "Cut nightly batch time by 40% by rewriting the ingestion service in Go and "
        "moving it to a queue-based design for 12 regional teams"
    )
    job = Experience(employer="Acme Corp", title="Senior Software Engineer", bullets=(bullet,))
    result = run(profile(experience=(job,)))
    assert result.profile.experience[0].bullets == (bullet,)
    assert result.dropped == []


def test_invented_bullet_dropped() -> None:
    job = Experience(
        employer="Acme Corp",
        title="Senior Software Engineer",
        bullets=("Won the company hackathon with a machine learning chatbot",),
    )
    assert run(profile(experience=(job,))).profile.experience[0].bullets == ()


def test_FR011_unstated_current_dropped() -> None:
    stated = Experience(employer="Acme Corp", title="Senior Software Engineer", current=True)
    unstated = Experience(employer="Globex Ltd", title="Software Engineer", current=True)
    result = run(profile(experience=(stated, unstated)))
    assert [e.current for e in result.profile.experience] == [True, False]
    assert dropped_paths(result) == ["experience[1].current"]


def test_dates_must_appear_in_the_resume() -> None:
    job = Experience(
        employer="Globex Ltd",
        title="Software Engineer",
        start=YearMonth(2017, 6),  # "06/2017" is in the source
        end=YearMonth(2019, 3),  # 2019 and March 2019 are not
    )
    result = run(profile(experience=(job,)))
    kept = result.profile.experience[0]
    assert (kept.start, kept.end) == (YearMonth(2017, 6), None)
    assert dropped_paths(result) == ["experience[0].end"]


def test_year_only_and_month_name_dates_match() -> None:
    job = Experience(
        employer="Acme Corp", title="Senior Software Engineer", start=YearMonth(2021, 1)
    )
    edu = Education(
        institution="Example Institute of Technology", start=YearMonth(2013), end=YearMonth(2017)
    )
    result = run(profile(experience=(job,), education=(edu,)))
    assert result.dropped == []


def test_invented_qualification_is_cleared_but_the_institution_stays() -> None:
    edu = Education(institution="Example Institute of Technology", qualification="PhD Physics")
    result = run(profile(education=(edu,)))
    assert result.profile.education[0].institution == "Example Institute of Technology"
    assert result.profile.education[0].qualification is None
    assert dropped_paths(result) == ["education[0].qualification"]


def test_planted_institution_certification_and_project_dropped() -> None:
    result = run(
        profile(
            education=(Education(institution="Hogwarts"),),
            certifications=(Certification(name="CISSP"),),
            projects=(Project(name="Skynet"),),
        )
    )
    assert result.profile.education == ()
    assert result.profile.certifications == ()
    assert result.profile.projects == ()
    assert dropped_paths(result) == ["education[0]", "projects[0]", "certifications[0]"]


def test_summary_must_match_the_resume() -> None:
    result = run(profile(summary="Visionary leader who single-handedly scaled three unicorns."))
    assert result.profile.summary is None
    assert result.dropped[0].path == "summary"
    assert result.dropped[0].reason == "summary not found in your resume"


def test_project_technologies_are_checked_like_skills() -> None:
    project = Project(name="Tracer", technologies=("Rust", "Haskell"))
    result = run(profile(projects=(project,)))
    assert result.profile.projects[0].technologies == ("Rust",)


def test_SC004_no_ungrounded_item_survives() -> None:
    planted_skills = ("Kubernetes", "Terraform", "Haskell", "Scala", "Swift", "COBOL")
    planted_employers = ("Initech", "Umbrella Corp", "Hooli")
    content = profile(
        skills=("Python", *planted_skills, "Go"),
        experience=tuple(
            Experience(employer=e, title="Software Engineer") for e in planted_employers
        ),
        certifications=(Certification(name="Made Up Cert"),),
    )
    result = run(content)
    source = normalize(SOURCE)
    for skill in result.profile.skills:
        assert normalize(skill) in source
    assert result.profile.experience == ()
    assert result.profile.certifications == ()
    assert len(result.dropped) == len(planted_skills) + len(planted_employers) + 1


def test_grounding_is_idempotent() -> None:
    content = profile(skills=("Python", "Kubernetes"))
    once = run(content)
    twice = run(once.profile)
    assert twice.profile == once.profile
    assert twice.dropped == []


def test_replace_keeps_untouched_parts_equal() -> None:
    content = profile(skills=("Python",))
    assert replace(run(content).profile) == content
