"""What the six fixed readers share: find the job links, take the lines that follow each one.

A reader knows a site's *link shape* and the order of the lines around a link (company, place).
It never guesses: a line the layout does not give stays ``None`` (FR-013). Small print (skills,
tags, "be an early applicant") is marked muted by the flattener and is not a candidate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Final

from hiretitan.mail.domain.alerts import (
    COMPANY_MAX,
    JOBS_PER_EMAIL_MAX,
    LINK_MAX,
    LOCATION_MAX,
    TITLE_MAX,
    AlertJob,
)
from hiretitan.mail.domain.links import is_job_link, posting_id
from hiretitan.mail.domain.mime import Flat, Link

CARD_LINES_MAX: Final = 6

# (the lines after the title, the link) -> (company, location)
Assign = Callable[[list[str], Link], tuple[str | None, str | None]]


def read_cards(site: str, flat: Flat, alert_date: datetime, assign: Assign) -> list[AlertJob]:
    """One job per distinct posting link, in the order the email lists them."""
    if flat.source != "html":
        return []  # a text part has no layout to rely on; the AI fallback reads it
    job_links = [link for link in flat.links if is_job_link(site, link.href)]
    jobs: list[AlertJob] = []
    seen: set[str] = set()
    for index, link in enumerate(job_links):
        pid = posting_id(site, link.href)
        if pid is None or pid in seen or not link.text or len(link.href) > LINK_MAX:
            continue
        seen.add(pid)
        end = job_links[index + 1].line if index + 1 < len(job_links) else len(flat.lines)
        card = [
            line.text
            for line in flat.lines[link.line + 1 : max(end, link.line + 1)][:CARD_LINES_MAX]
            if not line.muted
        ]
        company, location = assign(card, link)
        jobs.append(
            AlertJob(
                title=link.text[:TITLE_MAX],
                company=_limit(company, COMPANY_MAX),
                location=_limit(location, LOCATION_MAX),
                link=link.href,
                posting_id=pid,
                site=site,
                alert_date=alert_date,
            )
        )
        if len(jobs) >= JOBS_PER_EMAIL_MAX:
            break
    return jobs


def _limit(value: str | None, size: int) -> str | None:
    return value[:size] if value else None


def at(lines: list[str], index: int) -> str | None:
    return lines[index] if index < len(lines) else None
