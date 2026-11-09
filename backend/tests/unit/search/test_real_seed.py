"""T057: the shipped company list (`backend/seed/companies.yaml`).

These tests read the real file. They guard what must never ship: contact data, notes, and sources
HireTitan must not read.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hiretitan.search.application.seed import ALLOWED_FIELDS, read_seed
from hiretitan.search.domain.vendors import ENABLED_VENDORS

SEED = Path(__file__).resolve().parents[3] / "seed" / "companies.yaml"
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
# sites HireTitan never reads (constitution VII); their companies are checked by hand
NEVER_READ_HOSTS = ("linkedin.com", "wellfound.com", "naukri.com", "indeed.com", "glassdoor.com")


@pytest.fixture(scope="module")
def rows() -> list[dict[str, object]]:
    return read_seed(SEED)


def test_constitution_VIII_seed_has_only_company_columns(rows: list[dict[str, object]]) -> None:
    assert rows, "the shipped company list is empty"
    for row in rows:
        assert set(row) <= ALLOWED_FIELDS
    text = SEED.read_text("utf-8").lower()
    assert "@" not in text, "an email address is in the company list"
    assert "linkedin.com/in/" not in text, "a person's profile link is in the company list"


def test_seed_keys_are_unique_slugs(rows: list[dict[str, object]]) -> None:
    keys = [str(row["key"]) for row in rows]
    assert len(keys) == len(set(keys))
    assert all(SLUG.fullmatch(key) for key in keys)


def test_seed_has_the_whole_sheet(rows: list[dict[str, object]]) -> None:
    assert len(rows) == 62


def test_seed_boards_use_only_enabled_providers(rows: list[dict[str, object]]) -> None:
    for row in rows:
        if row.get("ats_vendor"):
            assert row["ats_vendor"] in ENABLED_VENDORS, row["key"]
            assert row["resolution"] == "verified", row["key"]


def test_seed_never_points_at_sites_we_do_not_read(rows: list[dict[str, object]]) -> None:
    for row in rows:
        host = (urlsplit(str(row.get("careers_url") or "")).hostname or "").lower()
        if any(host == site or host.endswith("." + site) for site in NEVER_READ_HOSTS):
            assert row["resolution"] == "check_manually", row["key"]


def test_seed_companies_without_a_careers_link_are_unresolved(
    rows: list[dict[str, object]],
) -> None:
    for row in rows:
        if not row.get("careers_url"):
            assert row["resolution"] == "unresolved", row["key"]
        if row["resolution"] == "careers_page":
            assert row.get("careers_url"), row["key"]
