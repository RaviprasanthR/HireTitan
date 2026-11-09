"""FR-040: nothing person-specific is hard-coded in the search code, seed data or prompts.

Locations, roles, pay and companies come from the person's settings and the neutral shipped list.
The values to look for are the maintainer's own, so they are never committed: the test reads them
from the gitignored ``docs/private/deny_values.txt`` (one value per line) when that file exists
and checks nothing otherwise. Without the file the scanner is still proven on planted text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
SCANNED = (
    BACKEND / "src" / "hiretitan" / "search",
    BACKEND / "src" / "hiretitan" / "prompts" / "judge_relevance",
    BACKEND / "src" / "hiretitan" / "prompts" / "extract_jobs_from_page",
    BACKEND / "seed",
)
SUFFIXES = {".py", ".yaml", ".yml", ".md", ".j2"}
DENY_FILE = ROOT / "docs" / "private" / "deny_values.txt"


def find_hits(text: str, values: list[str]) -> list[str]:
    lowered = text.lower()
    return [v for v in values if v.lower() in lowered]


def _files() -> list[Path]:
    found: list[Path] = []
    for base in SCANNED:
        if base.is_dir():
            found.extend(p for p in base.rglob("*") if p.suffix in SUFFIXES and p.is_file())
    return found


def test_FR040_scanner_finds_a_planted_value() -> None:
    assert find_hits("Jobs in Examplecity only", ["examplecity"]) == ["examplecity"]
    assert find_hits("nothing here", ["examplecity"]) == []


def test_FR040_search_code_and_seed_hard_code_no_person_specific_values() -> None:
    if not DENY_FILE.is_file():
        pytest.skip("no docs/private/deny_values.txt on this machine")
    values = [v.strip() for v in DENY_FILE.read_text("utf-8").splitlines() if v.strip()]
    hits = {
        str(path.relative_to(ROOT)): found
        for path in _files()
        if (found := find_hits(path.read_text("utf-8"), values))
    }
    assert not hits, f"person-specific values found: {sorted(hits)}"
