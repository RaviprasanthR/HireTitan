"""Cutshort job alerts: the title link, then one line, "Company · Place" (or the company alone)."""

from __future__ import annotations

from datetime import datetime

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat, Link
from hiretitan.mail.domain.readers.common import at, read_cards


def _assign(lines: list[str], _link: Link) -> tuple[str | None, str | None]:
    line = at(lines, 0)
    if line is None:
        return None, None
    company, separator, place = line.partition(" · ")
    return (company.strip() or None), ((place.strip() or None) if separator else None)


def read(flat: Flat, alert_date: datetime) -> list[AlertJob]:
    return read_cards("cutshort", flat, alert_date, _assign)
