"""Which areas a job title counts in (feature 002b, FR-017, SC-005; research R6)."""

from __future__ import annotations

import csv
from pathlib import Path

from hiretitan.search.domain.job_area import areas_of

LABELLED = Path(__file__).parents[2] / "fixtures" / "sheets" / "job_titles_labelled.csv"


def test_FR017_full_stack_counts_for_front_end_and_back_end() -> None:
    assert areas_of("Senior Full Stack Engineer") == {"frontend", "backend"}
    assert areas_of("Fullstack Developer") == {"frontend", "backend"}
    assert areas_of("Full-Stack Software Engineer") == {"frontend", "backend"}


def test_FR017_unrelated_title_counts_nowhere() -> None:
    assert areas_of("Marketing Manager") == frozenset()
    assert areas_of("Senior Engineering Manager") == frozenset()


def test_FR017_go_counts_only_with_capital_G() -> None:
    assert areas_of("Senior Go Developer") == {"backend"}
    assert areas_of("senior go developer") == frozenset()
    assert areas_of("Let's Go-To-Market Manager") == frozenset()


def test_FR017_designer_excluded_unless_engineering_word() -> None:
    assert areas_of("Senior UI Designer") == frozenset()
    assert areas_of("UI Designer and Developer") == {"frontend"}


def test_FR017_front_end_spellings() -> None:
    for title in ("Frontend Engineer", "Front End Engineer", "Front-End Engineer"):
        assert areas_of(title) == {"frontend"}


def test_SC005_labelled_titles_95_percent() -> None:
    with LABELLED.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100
    misses = []
    for row in rows:
        want = frozenset() if row["areas"] == "none" else frozenset(row["areas"].split("|"))
        got = areas_of(row["title"])
        if got != want:
            misses.append((row["title"], sorted(want), sorted(got)))
    print("misses:", misses)
    assert len(rows) - len(misses) >= 95, misses
