"""Resume document, keyword match and tailoring checks (T022, T023): FR-015 to FR-018."""

from __future__ import annotations

from datetime import date

from tests.fakes.drafts_data import TECH_TERMS
from tests.fakes.drafts_env import synthetic_content

from hiretitan.drafts.domain.facts import drafting_facts, years_of_experience
from hiretitan.drafts.domain.keywords import backed, match
from hiretitan.drafts.domain.resume_doc import (
    BulletChoice,
    ExperienceChoice,
    ResumeChoice,
    build_from_profile,
    document_text,
    plain_reorder,
)
from hiretitan.drafts.domain.tailor_checks import check_choice
from hiretitan.drafts_wiring import profile_view

PROFILE = profile_view(synthetic_content())
NEWEST, OLDEST = PROFILE.experience
FACTS = drafting_facts(PROFILE)
NAMES = ("Northwind Labs", "Initech Works", "Lakeside University", "Acme", "Budget Tracker")


def problems(choice: ResumeChoice) -> list[str]:
    found = check_choice(
        choice,
        PROFILE,
        FACTS,
        tech_terms=TECH_TERMS,
        allowed_names=NAMES,
        years=years_of_experience(PROFILE, date(2026, 11, 17)),
        context="Backend Engineer Acme",
    )
    return [p.code for p in found]


def test_FR015_facts_copied_by_id_not_from_ai() -> None:
    choice = ResumeChoice(
        summary="Backend engineer who builds reliable APIs.",
        experience=(
            ExperienceChoice("not-a-real-id", (BulletChoice(0, "Invented a company"),)),
            ExperienceChoice(NEWEST.id, (BulletChoice(0, "Built a Python service at scale"),)),
        ),
        skills=("Python", "Cobol"),
    )

    doc = build_from_profile(PROFILE, choice)

    assert [(e.employer, e.title) for e in doc.experience] == [
        ("Northwind Labs", "Backend Engineer"),
        ("Initech Works", "Junior Developer"),
    ]
    assert doc.experience[0].dates == "Mar 2021 - Present"
    assert doc.experience[1].dates == "Jan 2019 - Feb 2021"
    assert doc.experience[0].bullets == ["Built a Python service at scale"]
    assert doc.experience[1].bullets == list(OLDEST.bullets)  # not chosen: kept as written
    assert "Cobol" not in doc.skills
    assert set(doc.skills) == set(PROFILE.skills)
    assert doc.contact.name == "Sam Rivera"
    assert [e.institution for e in doc.education] == ["Lakeside University"]
    assert [c.name for c in doc.certifications] == ["Cloud Basics"]


def test_US4_AS2_plain_reorder_has_every_fact() -> None:
    doc = plain_reorder(PROFILE, ["PostgreSQL", "Django"])

    text = "\n".join(document_text(doc))
    for job in PROFILE.experience:
        assert job.employer in text
        for bullet in job.bullets:
            assert bullet in text
    for skill in PROFILE.skills:
        assert skill in text
    assert doc.experience[0].bullets[0].startswith("Moved a PostgreSQL")  # the match first
    assert doc.skills[0] in ("PostgreSQL", "Django")


def test_FR017_only_backed_keywords_offered() -> None:
    wanted = ["Python", "Kubernetes", "PostgreSQL", "Terraform"]

    assert backed(wanted, PROFILE) == {"Python", "PostgreSQL"}


def test_FR017_match_and_missing_reasons() -> None:
    wanted = ["Python", "Kubernetes", "PostgreSQL", "Django"]
    can_claim = backed(wanted, PROFILE)
    doc = plain_reorder(PROFILE, wanted)
    shortened = doc.model_copy(update={"skills": ["Python"], "experience": []})

    full = match(wanted, document_text(doc), can_claim)
    partial = match(wanted, document_text(shortened), can_claim)

    assert set(full.matched) == {"Python", "PostgreSQL", "Django"}
    assert [(m.keyword, m.reason) for m in full.missing] == [("Kubernetes", "not_in_profile")]
    assert full.score == 0.75
    assert ("PostgreSQL", "not_in_resume") in [(m.keyword, m.reason) for m in partial.missing]


def test_FR018_document_text_reading_order() -> None:
    lines = document_text(plain_reorder(PROFILE, []))

    order = ["Sam Rivera", "Summary", "Experience", "Skills", "Projects", "Education"]
    positions = [lines.index(heading) for heading in order]
    assert positions == sorted(positions)
    assert lines.index("Certifications") > positions[-1]
    assert lines.index("Backend Engineer, Northwind Labs") < lines.index(
        "Junior Developer, Initech Works"
    )


def test_FR015_bullet_number_not_in_source_rejected() -> None:
    bad = ResumeChoice(
        summary="Backend engineer.",
        experience=(
            ExperienceChoice(NEWEST.id, (BulletChoice(0, "Built a Python service for 400 users"),)),
        ),
    )
    good = ResumeChoice(
        summary="Backend engineer.",
        experience=(
            ExperienceChoice(
                NEWEST.id,
                (BulletChoice(0, "Built a Python service handling 40 requests per second"),),
            ),
        ),
    )

    assert "number" in problems(bad)
    assert problems(good) == []


def test_FR015_bullet_technology_not_in_source_rejected() -> None:
    bad = ResumeChoice(
        summary="Backend engineer.",
        experience=(
            ExperienceChoice(
                NEWEST.id, (BulletChoice(0, "Deployed a Python service on Kubernetes"),)
            ),
        ),
    )

    assert "technology" in problems(bad)


def test_FR015_unknown_skill_rejected() -> None:
    assert "skill" in problems(ResumeChoice(summary="Engineer.", skills=("Python", "Cobol")))
    assert problems(ResumeChoice(summary="Engineer.", skills=("python", "Django"))) == []


def test_FR015_unknown_experience_id_rejected() -> None:
    choice = ResumeChoice(
        summary="Engineer.", experience=(ExperienceChoice("nope", (BulletChoice(0, "x"),)),)
    )
    out_of_range = ResumeChoice(
        summary="Engineer.", experience=(ExperienceChoice(NEWEST.id, (BulletChoice(9, "x"),)),)
    )

    assert "unknown_experience" in problems(choice)
    assert "unknown_bullet" in problems(out_of_range)
    assert "unknown_project" in problems(ResumeChoice(summary="Engineer.", project_ids=("zzz",)))


def test_FR015_summary_cannot_invent() -> None:
    assert "years" in problems(ResumeChoice(summary="Engineer with 15 years of experience."))
    assert "name" in problems(ResumeChoice(summary="Engineer who worked at Globex."))


def test_FR015_a_rewritten_bullet_cannot_add_an_employer_or_school() -> None:
    choice = ResumeChoice(
        summary="Backend engineer who builds reliable APIs.",
        experience=(
            ExperienceChoice(NEWEST.id, (BulletChoice(0, "Built a Python service for Globex"),)),
        ),
        skills=("Python",),
    )
    assert "name" in problems(choice)
