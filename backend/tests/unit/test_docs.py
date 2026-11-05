"""T068: the user guide's defaults table matches the code (FR-024)."""

from __future__ import annotations

from pathlib import Path

from hiretitan.preferences.domain.defaults import (
    DEFAULT_COUNTRY,
    DEFAULT_CURRENCY,
    DEFAULT_NOTICE_DAYS,
    default_preferences,
)

GUIDE = Path(__file__).resolve().parents[3] / "docs" / "user-guide" / "preference-defaults.md"


def documented_defaults() -> dict[str, str]:
    """Rows of the markdown table: ``| Setting | Default | Why |``."""
    rows: dict[str, str] = {}
    for line in GUIDE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and line.lstrip().startswith("|") and set(cells[0]) - {"-", " "}:
            rows[cells[0]] = cells[1].strip("`")
    rows.pop("Setting", None)
    return rows


def test_FR024_documented_defaults_match_code() -> None:
    doc = documented_defaults()
    prefs = default_preferences()

    assert doc["Country"] == DEFAULT_COUNTRY == prefs.default_country
    assert doc["Currency"] == DEFAULT_CURRENCY == prefs.pay.currency
    assert doc["Notice period (days)"] == str(DEFAULT_NOTICE_DAYS) == str(prefs.notice_period_days)
    assert set(doc["Work modes"].split(", ")) == set(prefs.work_modes)
    assert set(doc["Job types"].split(", ")) == set(prefs.job_types)
    assert doc["Pay basis"] == prefs.pay.basis
    assert doc["Willing to relocate"] == str(prefs.willing_to_relocate).lower()


def test_FR024_every_list_default_is_empty_and_documented() -> None:
    doc = documented_defaults()
    prefs = default_preferences()
    empty_lists = {
        "Target roles": prefs.target_roles,
        "Seniority levels": prefs.seniority_levels,
        "Key skills": prefs.key_skills,
        "Preferred locations": prefs.preferred_locations,
        "Blocked locations": prefs.blocked_locations,
        "Preferred companies": prefs.preferred_companies,
        "Companies to avoid": prefs.avoided_companies,
    }
    for name, value in empty_lists.items():
        assert doc[name] == "empty", name
        assert value == (), name
