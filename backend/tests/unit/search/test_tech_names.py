"""002i T010: a technology named in a job title that the person does not have (FR-032). Pure."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.search.application.tables_seed import load_tech_names
from hiretitan.search.domain.tech_names import names_in, stack_skip_reason

TABLE = load_tech_names(Path(__file__).resolve().parents[3] / "seed" / "tech_names.yaml")
PERSON = ["Python", "Go", "Erlang", "FastAPI", "PostgreSQL", "Docker"]


@pytest.mark.parametrize(
    ("title", "named"),
    [
        ("Senior Software Engineer - BackEnd ( Java )", ["Java"]),
        ("Java / Python Developer", ["Java", "Python"]),
        ("JavaScript Developer", ["JavaScript"]),  # Java is not found inside JavaScript
        ("Senior C# .NET Developer", ["C#"]),
        ("C++ Engineer", ["C++"]),
        ("Golang Developer", ["Go"]),
        ("Go Developer", ["Go"]),
        ("Backend Engineer (Go)", ["Go"]),
        ("Senior Spring Boot Developer", ["Spring"]),
        ("Node.js Engineer", ["Node.js"]),
        ("React Native Developer", ["React"]),
        ("Rust Engineer", ["Rust"]),
        ("Software Engineer", []),
        ("Software Development Engineer II", []),
    ],
)
def test_FR032_names_in_a_title(title: str, named: list[str]) -> None:
    assert list(names_in(title, TABLE)) == named


@pytest.mark.parametrize(
    "title",
    [
        "Spring 2027 Software Engineering Intern",  # a season, not the framework
        "Software Engineer, Spring 2027",  # the context word is next to it, still a season
        "Engineer - Spring 2027 Intern",
        "Engineering Spring Internship Program",
        "Swift Logistics Operations Manager",  # a company, not the language
        "Go To Market Engineer",  # not the language
        "Engineer, Go-to-Market Systems",
        "Rustic Furniture Designer",  # only whole words count
        "Javascripter",  # nothing is found inside a longer word
    ],
)
def test_FR032_ordinary_words_are_not_technologies(title: str) -> None:
    assert names_in(title, TABLE) == ()


def test_FR032_title_stack_rule() -> None:
    """A Java back end role is left out for a Python person, with a readable reason."""
    reason = stack_skip_reason("Senior Software Engineer - BackEnd ( Java )", PERSON, TABLE)
    assert reason == "needs Java, which is not in your skills"


def test_FR032_several_missing_technologies_are_listed() -> None:
    reason = stack_skip_reason("Java or Kotlin Developer", PERSON, TABLE)
    assert reason == "needs Java or Kotlin, which are not in your skills"
    three = stack_skip_reason("Java, Kotlin or Scala Developer", PERSON, TABLE)
    assert three == "needs Java, Kotlin or Scala, which are not in your skills"


def test_FR032_java_and_python_title_is_kept() -> None:
    assert stack_skip_reason("Java / Python Developer", PERSON, TABLE) is None


def test_FR032_no_tech_in_title_is_kept() -> None:
    assert stack_skip_reason("Senior Software Engineer", PERSON, TABLE) is None


def test_FR032_a_skill_written_another_way_still_counts() -> None:
    # "Golang" in the profile is the Go in the title; "Go" in the profile is "Golang" in the title
    assert stack_skip_reason("Golang Developer", ["Go"], TABLE) is None
    assert stack_skip_reason("Go Developer", ["Golang"], TABLE) is None
    assert stack_skip_reason("Senior Java Developer", ["Java (Spring Boot)"], TABLE) is None


def test_FR032_the_person_without_skills_is_not_filtered() -> None:
    """Nothing is known about the person's stack, so nothing is skipped on it."""
    assert stack_skip_reason("Senior Java Developer", [], TABLE) is None


def test_FR032_an_empty_table_skips_nothing() -> None:
    assert stack_skip_reason("Senior Java Developer", PERSON, ()) is None


def test_FR032_a_framework_title_is_kept_for_a_person_with_its_language() -> None:
    assert stack_skip_reason("Django Developer", ["Python"], TABLE) is None
    assert stack_skip_reason("Spring Boot Developer", ["Java"], TABLE) is None
    assert stack_skip_reason("React Developer", ["JavaScript"], TABLE) is None
    assert stack_skip_reason("Node.js Engineer", ["TypeScript"], TABLE) is None


def test_FR032_a_person_with_a_framework_has_its_language() -> None:
    assert stack_skip_reason("Java Developer", ["Spring Boot", "Docker"], TABLE) is None
    assert stack_skip_reason("Python Developer", ["Django"], TABLE) is None
    assert stack_skip_reason("JavaScript Developer", ["React"], TABLE) is None


def test_FR032_a_framework_of_another_language_is_still_left_out() -> None:
    reason = stack_skip_reason("Django Developer", ["Java", "Spring"], TABLE)
    assert reason == "needs Django, which is not in your skills"


def test_FR032_skills_with_no_language_or_framework_in_them_filter_nothing() -> None:
    """Nothing is known about this person's stack: a title naming a language does not skip."""
    assert stack_skip_reason("Analyst (Python)", ["SQL", "Tableau"], TABLE) is None
