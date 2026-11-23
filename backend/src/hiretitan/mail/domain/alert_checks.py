"""Check what the AI says about an alert email against the email itself (FR-013a). Pure.

The AI proposes a title, company, place and a link *number*. This turns that into alert jobs only
where the email backs it up:

* the link is taken from the email's own list by number; a number that was not on offer, a link that
  is not a web address, or a link already used for another job drops the job;
* the title must be words the email contains, or the job is dropped;
* a company or place that is not in the email is left empty, never kept (nothing is invented).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

from hiretitan.mail.domain.alerts import COMPANY_MAX, LOCATION_MAX, TITLE_MAX, AlertJob
from hiretitan.mail.domain.links import on_site, posting_id
from hiretitan.mail.domain.mime import Flat

JOBS_MAX: Final = 30
TITLE_MIN: Final = 3  # a title of a letter or two is never accepted
VALUE_MIN: Final = 2


@dataclass(frozen=True, slots=True)
class Proposed:
    """One job as the AI proposed it (``link_index`` counts from 1)."""

    title: str
    company: str | None
    location: str | None
    link_index: int


def _line(text: str) -> str:
    """One line of words: look-alike characters folded, one space between words."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _in_email(value: str | None, segments: Sequence[str], *, minimum: int) -> str | None:
    """The email's own writing of ``value``, when one line (or one link text) of the email holds
    it as whole words, in any letter case; otherwise None. A value is never stitched together from
    two lines, never a piece of a longer word, and what is kept is the email's wording."""
    if not value:
        return None
    needle = _line(value)
    if len(needle) < minimum:
        return None
    pattern = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", re.IGNORECASE)
    for segment in segments:
        found = pattern.search(segment)
        if found:
            return segment[found.start() : found.end()]
    return None


def _web_link(href: str) -> bool:
    parts = urlsplit(href)
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def accept(
    proposed: Sequence[Proposed],
    flat: Flat,
    *,
    site: str,
    alert_date: datetime,
    shown: int,
) -> list[AlertJob]:
    """The jobs the email backs up. ``shown`` is how many of its links the AI was given."""
    segments = [_line(line.text) for line in flat.lines]
    segments += [_line(link.text) for link in flat.links]
    jobs: list[AlertJob] = []
    used: set[int] = set()
    for item in proposed:
        index = item.link_index
        if not 1 <= index <= min(shown, len(flat.links)) or index in used:
            continue
        href = flat.links[index - 1].href
        title = _in_email(item.title, segments, minimum=TITLE_MIN)
        if title is None or not _web_link(href) or not on_site(site, href):
            continue
        used.add(index)
        company = _in_email(item.company, segments, minimum=VALUE_MIN)
        location = _in_email(item.location, segments, minimum=VALUE_MIN)
        jobs.append(
            AlertJob(
                title=title[:TITLE_MAX],
                company=company[:COMPANY_MAX] if company else None,
                location=location[:LOCATION_MAX] if location else None,
                link=href,
                posting_id=posting_id(site, href),
                site=site,
                alert_date=alert_date,
            )
        )
        if len(jobs) == JOBS_MAX:
            break
    return jobs
