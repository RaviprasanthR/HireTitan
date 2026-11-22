"""The one Gmail search a check sends (T023): FR-009, FR-011. Built from the sender list only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from hiretitan.mail.domain.senders import SenderError, build_query, window_start

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
