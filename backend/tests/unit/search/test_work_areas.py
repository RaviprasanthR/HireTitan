"""002i T011: guessing the person's area of work and the title words to avoid for other areas.

Pure and deterministic (research R5): the same reviewed table decides, nothing is asked of an AI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.search.application.tables_seed import load_work_areas
from hiretitan.search.domain.rules import AREAS_MAX, ITEM_TEXT_MAX
from hiretitan.search.domain.work_areas import avoid_words, guess_areas

TABLE = load_work_areas(Path(__file__).resolve().parents[3] / "seed" / "work_areas.yaml")

BACK_END_SKILLS = ("Python", "Go", "FastAPI", "PostgreSQL", "REST APIs", "Docker")


def test_FR030_a_back_end_person_is_back_end() -> None:
    areas = guess_areas(
        ("Backend Engineer", "SDE"),
        ("Software Engineer", "Backend Developer"),
        BACK_END_SKILLS,
        TABLE,
    )
    assert areas == ("back_end",)


def test_FR030_generic_titles_are_decided_by_the_skills() -> None:
    """Ravi's case: the roles say "software engineer", so the skills say what kind."""
    skills = (
        "Python",
        "Go",
        "Erlang",
        "FastAPI",
        "REST APIs",
        "Microservices",
        "PostgreSQL",
        "MySQL",
        "ELT Pipelines",
        "dbt",
        "Docker",
        "Kubernetes",
        "Jenkins",
        "Linux",
        "Git",
    )
    assert guess_areas(("software engineer", "sde"), (), skills, TABLE) == ("back_end",)


def test_FR030_a_front_end_person_is_front_end() -> None:
    areas = guess_areas(("Frontend Developer",), (), ("React", "TypeScript", "CSS"), TABLE)
    assert areas == ("front_end",)


def test_FR030_full_stack_title_gives_full_stack() -> None:
    areas = guess_areas(("Full Stack Developer",), (), ("Python", "React", "PostgreSQL"), TABLE)
    assert "full_stack" in areas


def test_FR030_close_scores_keep_both_areas() -> None:
    areas = guess_areas((), (), ("React", "TypeScript", "Python", "PostgreSQL"), TABLE)
    assert set(areas) == {"front_end", "back_end"}


def test_FR030_at_most_the_limit_and_never_other() -> None:
    skills = ("React", "Python", "Android", "Selenium", "Kubernetes", "dbt", "Airflow", "Spark")
    areas = guess_areas((), (), skills, TABLE)
    assert len(areas) <= AREAS_MAX
    assert "other" not in areas


def test_FR030_no_signal_gives_no_area() -> None:
    assert guess_areas(("Chief Llama Wrangler",), (), ("Knitting",), TABLE) == ()
    assert guess_areas((), (), (), TABLE) == ()


def test_FR030_whole_words_only() -> None:
    # "go" must not be found inside "google"; "ios" not inside "bios"
    assert guess_areas((), (), ("Google Docs", "BIOS tuning"), TABLE) == ()


def test_FR031_avoid_words_for_other_areas() -> None:
    words = avoid_words(("back_end",), TABLE)
    for expected in ("frontend", "front end", "android", "ios", "qa", "sdet"):
        assert expected in words
    # a back end person is not put off by data, devops or full stack titles
    assert "devops" not in words
    assert "data scientist" not in words
    assert not {"backend", "back end"} & set(words)  # never the person's own area


def test_FR031_full_stack_avoids_neither_front_nor_back_end() -> None:
    words = avoid_words(("full_stack",), TABLE)
    assert "frontend" not in words
    assert "backend" not in words
    assert "android" in words  # but still not mobile or QA


def test_FR031_two_areas_avoid_what_neither_goes_with() -> None:
    words = avoid_words(("back_end", "front_end"), TABLE)
    assert "frontend" not in words
    assert "backend" not in words
    assert "android" not in words  # mobile goes with front end


def test_FR031_no_area_means_no_avoid_words() -> None:
    assert avoid_words((), TABLE) == ()


def test_FR031_words_are_unique_short_and_in_a_stable_order() -> None:
    words = avoid_words(("back_end",), TABLE)
    assert len(words) == len(set(words))
    assert all(0 < len(w) <= ITEM_TEXT_MAX for w in words)
    assert words == avoid_words(("back_end",), TABLE)


@pytest.mark.parametrize(
    "area", sorted({"back_end", "front_end", "mobile", "data", "qa", "devops"})
)
def test_FR031_a_person_in_an_area_never_avoids_its_own_words(area: str) -> None:
    own = set(TABLE[area].avoid_in_titles)
    assert not own & set(avoid_words((area,), TABLE))
