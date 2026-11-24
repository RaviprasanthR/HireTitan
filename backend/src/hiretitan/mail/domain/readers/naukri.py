"""Naukri job alerts: the title link, the company, an experience range ("3-7 Yrs"), the place."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Final

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat, Link
from hiretitan.mail.domain.readers.common import at, read_cards

_DASHES: Final = "-" + chr(0x2013)  # a hyphen or an en dash separates the years
_EXPERIENCE: Final = re.compile(
    r"^\d+\s*[" + _DASHES + r"]\s*\d+\s*(?:yrs?|years?)\.?$", re.IGNORECASE
)


def _assign(lines: list[str], _link: Link) -> tuple[str | None, str | None]:
    rest = [line for line in lines[1:] if not _EXPERIENCE.match(line)]
    return at(lines, 0), at(rest, 0)


def read(flat: Flat, alert_date: datetime) -> list[AlertJob]:
    return read_cards("naukri", flat, alert_date, _assign)
