"""T008: the clock port. Time is always timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from hiretitan.platform.clock import ClockPort, FakeClock, SystemClock


def test_fake_clock_advances_utc() -> None:
    start = datetime(2026, 11, 4, 9, 30, tzinfo=UTC)
    clock = FakeClock(start)

    assert clock.now() == start
    clock.advance(timedelta(minutes=5))
    assert clock.now() == start + timedelta(minutes=5)
    assert clock.now().tzinfo is UTC


def test_fake_clock_defaults_to_fixed_utc_instant() -> None:
    assert FakeClock().now().tzinfo is UTC


def test_fake_clock_converts_other_offsets_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    clock = FakeClock(datetime(2026, 11, 4, 15, 0, tzinfo=ist))
    assert clock.now() == datetime(2026, 11, 4, 9, 30, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


def test_fake_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FakeClock(datetime(2026, 11, 4, 9, 30))  # noqa: DTZ001 - the point of the test


def test_fake_clock_cannot_go_backwards() -> None:
    with pytest.raises(ValueError, match="backwards"):
        FakeClock().advance(timedelta(seconds=-1))


def test_system_clock_returns_aware_utc_now() -> None:
    before = datetime.now(UTC)
    now = SystemClock().now()
    assert now.tzinfo is UTC
    assert before <= now <= datetime.now(UTC)


def test_both_clocks_satisfy_the_port() -> None:
    clocks: list[ClockPort] = [SystemClock(), FakeClock()]
    assert all(isinstance(c, ClockPort) for c in clocks)
