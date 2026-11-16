"""002i T004: the shipped work-area and technology tables, and their fail-fast loaders."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.search.application.tables_seed import (
    TablesError,
    load_tech_names,
    load_work_areas,
)
from hiretitan.search.domain.rules import AREAS

SEED = Path(__file__).resolve().parents[3] / "seed"

_ALL_AREAS = "".join(
    f"  {name}:\n    signals: [a]\n    avoid_in_titles: []\n    compatible: []\n"
    for name in sorted(AREAS)
)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "table.yaml"
    path.write_text(text, "utf-8")
    return path


def test_work_areas_table_loads_and_is_consistent() -> None:
    table = load_work_areas(SEED / "work_areas.yaml")
    assert set(table) == set(AREAS)  # every area is described
    for name, entry in table.items():
        assert entry.name == name
        assert set(entry.compatible) <= set(AREAS) - {name}
    # the areas a back end person wants left out have words to avoid
    assert "frontend" in table["front_end"].avoid_in_titles
    assert "android" in table["mobile"].avoid_in_titles
    assert "sdet" in table["qa"].avoid_in_titles
    assert table["full_stack"].avoid_in_titles == ()  # a full stack title is never avoided


def test_tech_names_have_unique_aliases() -> None:
    table = load_tech_names(SEED / "tech_names.yaml")
    names = {t.name for t in table}
    assert {"Java", "JavaScript", "Python", "Go", "React"} <= names
    seen: set[str] = set()
    for tech in table:
        for word in (tech.name, *tech.aliases):
            key = " ".join(word.lower().split())
            assert key not in seen, key
            seen.add(key)
    go = next(t for t in table if t.name == "Go")
    assert go.context  # an ordinary word, so it needs a context word next to it


def test_a_complete_small_table_loads(tmp_path: Path) -> None:
    table = load_work_areas(write(tmp_path, "areas:\n" + _ALL_AREAS))
    assert set(table) == set(AREAS)


@pytest.mark.parametrize(
    "text",
    [
        "areas: [back_end]",  # not a mapping of areas
        "areas:\n  backend:\n    signals: []\n    avoid_in_titles: []\n    compatible: []\n",
        "areas:\n" + _ALL_AREAS.replace("    compatible: []\n", "", 1),  # a field missing
        "areas:\n" + _ALL_AREAS.replace("signals: [a]", "signals: oops", 1),  # not a list
        "areas:\n" + _ALL_AREAS.replace("avoid_in_titles: []", "avoid_in_titles: ['']", 1),
        "areas:\n" + _ALL_AREAS.replace("compatible: []", "compatible: [nope]", 1),
        "areas:\n" + _ALL_AREAS.replace("compatible: []", "compatible: [back_end]", 1),  # itself?
        "areas:\n  back_end:\n    signals: [a]\n    avoid_in_titles: []\n    compatible: []\n",
        "not: [valid",  # broken YAML
    ],
)
def test_seed_tables_reject_bad_files_work_areas(tmp_path: Path, text: str) -> None:
    with pytest.raises(TablesError):
        load_work_areas(write(tmp_path, text))


@pytest.mark.parametrize(
    "text",
    [
        "technologies: oops",
        "technologies:\n  - {name: Java, kind: language, aliases: [jvm]}\n"
        "  - {name: Kotlin, kind: language, aliases: [JVM]}\n",  # a duplicate alias
        "technologies:\n  - {name: Java, kind: language, aliases: []}\n"
        "  - {name: java, kind: language, aliases: []}\n",  # a duplicate name
        "technologies:\n  - {name: Java, kind: tool, aliases: []}\n",  # unknown kind
        "technologies:\n  - {name: '', kind: language, aliases: []}\n",
        "technologies:\n  - {name: Java, kind: language}\n",  # aliases missing
        "technologies:\n  - {name: Go, kind: language, aliases: [], context: oops}\n",
        "{broken",
    ],
)
def test_seed_tables_reject_bad_files_tech_names(tmp_path: Path, text: str) -> None:
    with pytest.raises(TablesError):
        load_tech_names(write(tmp_path, text))


def test_missing_file_is_a_tables_error(tmp_path: Path) -> None:
    with pytest.raises(TablesError):
        load_work_areas(tmp_path / "missing.yaml")


def test_implied_languages_are_known_names(tmp_path: Path) -> None:
    ok = (
        "technologies:\n"
        "  - {name: Python, kind: language, aliases: []}\n"
        "  - {name: Django, kind: framework, aliases: [], implies: [Python]}\n"
    )
    table = load_tech_names(write(tmp_path, ok))
    assert next(t for t in table if t.name == "Django").implies == ("Python",)
    bad = ok.replace("implies: [Python]", "implies: [Cobol]")
    with pytest.raises(TablesError):
        load_tech_names(write(tmp_path, bad))


def test_the_shipped_frameworks_name_their_languages() -> None:
    table = load_tech_names(SEED / "tech_names.yaml")
    by_name = {t.name: t for t in table}
    assert "Python" in by_name["Django"].implies
    assert "Java" in by_name["Spring"].implies
    assert "JavaScript" in by_name["React"].implies
