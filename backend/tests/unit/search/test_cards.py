"""002i T012: what the relevance check is told about the person and about each job (FR-033)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from hiretitan.search.application.tables_seed import load_tech_names
from hiretitan.search.domain.cards import (
    KEY_SKILLS_MAX,
    RECENT_TITLES_MAX,
    JobCardInput,
    ProfileCard,
    job_cards,
    main_skills,
)

TECH = load_tech_names(Path(__file__).resolve().parents[3] / "seed" / "tech_names.yaml")


def card(**changes: object) -> ProfileCard:
    base = {
        "target_roles": ("Backend Engineer",),
        "seniority": (),
        "years_experience": Decimal("4.5"),
        "key_skills": ("Python",),
        "preferred_locations": (),
        "work_modes": ("remote",),
    }
    return ProfileCard(**{**base, **changes})  # type: ignore[arg-type]


def test_FR033_languages_come_first() -> None:
    skills = main_skills(("Docker",), ("Linux", "Python", "docker", "Go"), TECH)
    assert skills == ("Python", "Go", "Docker", "Linux")


def test_FR033_skills_are_deduplicated_ignoring_case_and_blanks() -> None:
    assert main_skills(("python", " "), ("Python", "PYTHON", ""), TECH) == ("python",)


def test_FR033_a_skill_that_mentions_a_language_counts_as_one() -> None:
    assert main_skills((), ("Kubernetes", "Java (Spring Boot)"), TECH) == (
        "Java (Spring Boot)",
        "Kubernetes",
    )


def test_FR033_card_limits() -> None:
    many = card(
        key_skills=tuple(f"skill {i}" for i in range(50)),
        recent_titles=tuple(f"Title {i}" for i in range(6)),
        areas=("back_end",),
    ).to_dict()
    assert len(many["key_skills"]) == KEY_SKILLS_MAX == 30
    assert len(many["recent_titles"]) == RECENT_TITLES_MAX == 3
    assert many["areas"] == ["back_end"]


def test_FR033_empty_new_fields_are_left_out() -> None:
    """Older prompt versions see the card exactly as before."""
    assert set(card().to_dict()) == {
        "target_roles",
        "seniority",
        "years_experience",
        "key_skills",
        "preferred_locations",
        "work_modes",
    }


def test_FR033_job_card_says_whether_the_description_was_read() -> None:
    def job(status: str) -> JobCardInput:
        return JobCardInput(
            title="Software Engineer",
            company="Acme",
            location=None,
            work_mode=None,
            skills_found=(),
            years_found=None,
            description="Build services." if status == "read" else "",
            description_status=status,  # type: ignore[arg-type]
        )

    cards, _ = job_cards([job("read"), job("unreadable"), job("none")])
    assert [c["description_status"] for c in cards] == ["read", "unreadable", "none"]
    assert cards[0]["excerpt"] == "Build services."


def test_FR033_a_job_card_without_a_status_is_none() -> None:
    plain = JobCardInput("T", "C", None, None, (), None, "")
    cards, _ = job_cards([plain])
    assert cards[0]["description_status"] == "none"
