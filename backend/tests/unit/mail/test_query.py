"""The one Gmail search a check sends (T023): FR-009, FR-011. Built from the sender list only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from hiretitan.mail.domain.senders import (
    SITE_DOMAINS,
    SenderError,
    build_query,
    is_sender_query,
    site_for_address,
    window_start,
)

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def test_FR009_query_only_enabled_senders() -> None:
    query = build_query(["alerts@naukri.example.invalid", "jobs@linkedin.example.invalid"], NOW)

    assert query == (
        "from:(alerts@naukri.example.invalid OR jobs@linkedin.example.invalid)"
        f" after:{int((NOW - timedelta(hours=24)).timestamp())}"
    )


def test_FR009_senders_are_sorted_and_repeats_dropped() -> None:
    query = build_query(["b@x.example.invalid", "a@x.example.invalid", "b@x.example.invalid"], NOW)

    assert query.startswith("from:(a@x.example.invalid OR b@x.example.invalid) after:")


def test_FR011_after_is_start_minus_24h() -> None:
    assert window_start(NOW) == NOW - timedelta(hours=24)
    local = datetime(2026, 11, 18, 14, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert window_start(local) == local - timedelta(hours=24)
    assert build_query(["a@x.example.invalid"], local).endswith(
        f"after:{int((local - timedelta(hours=24)).timestamp())}"
    )


def test_FR009_no_senders_means_no_query() -> None:
    with pytest.raises(SenderError):
        build_query([], NOW)


@pytest.mark.parametrize(
    "bad",
    [
        'a" OR in:anywhere@x.example.invalid',
        "a@x.example.invalid) OR (label:inbox",
        "-a@x.example.invalid",
        "a@x.example.invalid OR b@y.example.invalid",
        "{a@x.example.invalid}",
        "subject:secret@x.example.invalid",
    ],
)
def test_FR009_no_free_text_in_query(bad: str) -> None:
    with pytest.raises(SenderError):
        build_query([bad], NOW)


def test_FR009_a_time_without_a_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        build_query(["a@x.example.invalid"], datetime(2026, 11, 18, 9, 0))  # noqa: DTZ001


def test_FR009_a_site_domain_is_asked_for_next_to_the_addresses() -> None:
    query = build_query(["a@x.example.invalid"], NOW, domains=["naukri.com", "indeed.com"])

    assert query == (
        "from:(a@x.example.invalid OR indeed.com OR naukri.com)"
        f" after:{int((NOW - timedelta(hours=24)).timestamp())}"
    )
    assert is_sender_query(query)


def test_FR009_only_a_built_in_site_domain_can_be_asked_for() -> None:
    for bad in ["gmail.com", "example.org", "naukri.com OR in:anywhere", "-naukri.com", "com"]:
        with pytest.raises(SenderError):
            build_query(["a@x.example.invalid"], NOW, domains=[bad])
    assert not is_sender_query("from:(gmail.com) after:1700000000")
    assert not is_sender_query("from:(a@x.example.invalid OR evil.example) after:1700000000")


def test_FR009_a_query_of_domains_alone_is_allowed() -> None:
    query = build_query([], NOW, domains=["naukri.com"])

    assert query.startswith("from:(naukri.com) after:")


def test_FR009_every_built_in_site_has_its_domain() -> None:
    assert set(SITE_DOMAINS) == {
        "linkedin",
        "naukri",
        "indeed",
        "foundit",
        "instahyre",
        "cutshort",
    }
    assert SITE_DOMAINS["naukri"] == ("naukri.com",)


@pytest.mark.parametrize(
    ("address", "site"),
    [
        ("alerts@naukri.com", "naukri"),
        ("noreply@mail.naukri.com", "naukri"),  # a sub-domain of the site's domain
        ("NOREPLY@Indeed.com", "indeed"),
        ("x@evilnaukri.com", None),  # not the site's domain
        ("x@naukri.com.evil.example", None),
        ("x@naukri.co", None),
        ("naukri.com", None),  # not an address
        ("", None),
    ],
)
def test_FR009_the_site_an_address_belongs_to_by_its_domain(address: str, site: str | None) -> None:
    assert site_for_address(address, {"naukri", "indeed", "linkedin"}) == site


def test_FR009_a_site_that_is_switched_off_owns_no_domain() -> None:
    assert site_for_address("alerts@naukri.com", {"indeed"}) is None
