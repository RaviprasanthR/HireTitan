"""Sign-ins that have started and not yet come back: one-time ``state`` values, kept 10 minutes.

Held in memory: one person, one process. A restart in the middle of a sign-in only means pressing
Connect again.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from hiretitan.mail.domain.oauth import new_state
from hiretitan.platform.clock import ClockPort

TTL: Final = timedelta(minutes=10)
MAX_PENDING: Final = 20


class PendingConsents:
    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock
        self._pending: dict[str, tuple[str, datetime]] = {}

    def start(self, verifier: str) -> str:
        """A new ``state`` for a sign-in that will need ``verifier`` when it comes back."""
        now = self._clock.now()
        self._pending = {s: v for s, v in self._pending.items() if v[1] > now}
        while len(self._pending) >= MAX_PENDING:
            self._pending.pop(next(iter(self._pending)))
        state = new_state()
        self._pending[state] = (verifier, now + TTL)
        return state

    def take(self, state: str | None) -> str | None:
        """The verifier for this ``state``, once; ``None`` if unknown, used or expired."""
        entry = self._pending.pop(state, None) if state else None
        if entry is None or entry[1] <= self._clock.now():
            return None
        return entry[0]

    def clear(self) -> None:
        """Forget every sign-in still open (Disconnect)."""
        self._pending.clear()
