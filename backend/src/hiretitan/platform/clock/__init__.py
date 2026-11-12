"""Clock port: the only way application code reads the current time.

All instants are timezone-aware UTC. Tests use ``FakeClock`` so time-based rules
(autosave, run timestamps) are deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

__all__ = ["ClockPort", "FakeClock", "SystemClock"]

_DEFAULT_FAKE_START = datetime(2026, 1, 1, tzinfo=UTC)


@runtime_checkable
class ClockPort(Protocol):
    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime = _DEFAULT_FAKE_START) -> None:
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("FakeClock needs a timezone-aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        if delta < timedelta(0):
            raise ValueError("FakeClock cannot go backwards")
        self._now += delta
