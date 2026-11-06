"""T023: the normalizer turns a cleaned posting into job fields without guessing (FR-027)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hiretitan.search.domain.normalize import canonical_url, normalize_job


def make(**changes: object):  # type: ignore[no-untyped-def]
    base = {
        "title": "Backend Engineer",
        "url": "https://boards.example.com/acme/jobs/123",
        "location_text": None,
        "posted_at": None,
        "description": "",
        "requisition_id": None,
        "stack_keywords": (),
    }
    return normalize_job(**{**base, **changes})  # type: ignore[arg-type]


def test_FR027_missing_location_stays_null() -> None:
    job = make(location_text=None)
    assert (job.city, job.country, job.work_mode, job.location_text) == (None, None, None, None)
    assert make(location_text="   ").location_text is None


def test_FR027_unknown_place_is_not_guessed() -> None:
    job = make(location_text="Somewhere Unlisted")
    assert (job.city, job.country) == (None, None)


def test_city_and_country_come_from_aliases() -> None:
    job = make(location_text="Bangalore, Karnataka, India")
    assert (job.city, job.country) == ("Bengaluru", "IN")
    assert make(location_text="Gurgaon").city == "Gurugram"
    assert make(location_text="London, United Kingdom").country == "GB"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "HTTPS://Boards.Example.com/Acme/Jobs/123/?utm_source=x&gh_src=y#apply",
            "https://boards.example.com/Acme/Jobs/123",
        ),
        ("https://x.example/jobs?id=7&utm_medium=mail", "https://x.example/jobs?id=7"),
        ("https://x.example/jobs?b=2&a=1", "https://x.example/jobs?a=1&b=2"),
        ("https://x.example/", "https://x.example/"),
    ],
)
def test_canonical_url_strips_tracking_and_fragment(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_canonical_url_of_junk_is_none() -> None:
    assert canonical_url("not a url") is None
    assert canonical_url("javascript:alert(1)") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("We need 3+ years of experience", Decimal(3)),
        ("5-8 years in backend work", Decimal(5)),
        ("minimum 2 years", Decimal(2)),
        ("1 year of Python", Decimal(1)),
        ("10 to 12 years", Decimal(10)),
        ("A friendly team", None),
        ("Founded 12 months ago", None),
    ],
)
def test_years_found_patterns(text: str, expected: Decimal | None) -> None:
    assert make(description=text).years_found == expected


@pytest.mark.parametrize(
    ("location", "title", "expected"),
    [
        ("Remote - India", "Engineer", "remote"),
        ("Pune (Hybrid)", "Engineer", "hybrid"),
        ("Pune, On-site", "Engineer", "onsite"),
        ("Pune", "Engineer (Remote)", "remote"),
        ("Remote or hybrid", "Engineer", "hybrid"),
        ("Pune", "Engineer", None),
    ],
)
def test_work_mode_only_when_stated(location: str, title: str, expected: str | None) -> None:
    assert make(location_text=location, title=title).work_mode == expected


def test_work_mode_is_not_taken_from_the_description() -> None:
    assert make(description="We have a remote-first culture").work_mode is None


def test_skills_found_uses_word_boundaries_and_both_title_and_description() -> None:
    job = make(
        title="Python Developer",
        description="You know FastAPI and C++, not JavaScript. Javascript is a different job.",
        stack_keywords=("python", "Java", "FastAPI", "C++", "Go"),
    )
    assert job.skills_found == ("python", "FastAPI", "C++")


def test_other_fields_pass_through() -> None:
    when = datetime(2026, 11, 1, tzinfo=UTC)
    job = make(posted_at=when, requisition_id="R-9")
    assert job.posted_at == when
    assert job.requisition_id == "R-9"
    assert job.canonical_url == "https://boards.example.com/acme/jobs/123"
