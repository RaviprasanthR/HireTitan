"""Instahyre job alerts: the title link, then the company and the place, either of which may be left
out of the email. When only one line is there, the address of the posting tells which it is
(``/job-<id>-<title>-at-<company>-<place>/``); the address only *classifies* the line, it never
supplies a value the email did not show."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat, Link
from hiretitan.mail.domain.readers.common import at, read_cards


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _company_and_place_slug(link: Link) -> str | None:
    """The part of the address after ``-at-``: the company, then the place."""
    path = _slug(urlsplit(link.href).path)
    marker = f"-{_slug(link.text)}-at-"
    _head, found, rest = path.partition(marker)
    return rest if found and rest else None


def _assign(lines: list[str], link: Link) -> tuple[str | None, str | None]:
    if len(lines) >= 2:
        return lines[0], lines[1]
    only = at(lines, 0)
    if only is None:
        return None, None
    rest = _company_and_place_slug(link)
    slug = _slug(only)
    if rest and not rest.startswith(slug + "-") and rest.endswith("-" + slug):
        return None, only  # the company was left out; what is shown is the place
    return only, None


def read(flat: Flat, alert_date: datetime) -> list[AlertJob]:
    return read_cards("instahyre", flat, alert_date, _assign)
