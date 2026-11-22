"""foundit job alerts: the title link, the company, the place (then small print)."""

from __future__ import annotations

from datetime import datetime

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat, Link
from hiretitan.mail.domain.readers.common import at, read_cards


def _assign(lines: list[str], _link: Link) -> tuple[str | None, str | None]:
    return at(lines, 0), at(lines, 1)


def read(flat: Flat, alert_date: datetime) -> list[AlertJob]:
    return read_cards("foundit", flat, alert_date, _assign)
