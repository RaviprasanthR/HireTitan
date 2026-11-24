"""Count a day's job-alert emails per sender and reader: ``python -m hiretitan.mail_counts``.

For checking the readers against real mail without sharing it (T047). Run it where HireTitan
runs, with Gmail connected:

    docker compose exec worker python -m hiretitan.mail_counts

It sends the query a check sends (the enabled senders and site domains, the last 24 hours), reads
each email with the fixed readers and prints only counts: emails and jobs per sender and reader.
No title, company, place or link is printed; an address that is not a listed sender is masked.
It stores nothing, marks nothing read and calls no AI (an email the AI would read is counted as
"AI needed").
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from hiretitan.mail.application.ports import MailReader
from hiretitan.mail.domain.senders import build_query, domains_of, site_for_address
from hiretitan.mail.domain.skeleton import mask
from hiretitan.mail.workflow.check import read_email_flat

LIST_MAX = 200

_READER_OF_OUTCOME = {
    "needs_ai": "AI needed",
    "unreadable": "AI needed",
    "no_jobs": "no jobs",
}


@dataclass(frozen=True, slots=True)
class CountRow:
    sender: str  # a listed sender as is; any other address masked
    reader: str  # the site whose reader read it, "AI needed", "no jobs" or "not a job site"
    emails: int
    jobs: int


async def count_alerts(
    reader: MailReader, site_of: Mapping[str, str], sites: frozenset[str], now: datetime
) -> list[CountRow]:
    """The counts for the last 24 hours, one row per sender and reader."""
    if not site_of:
        return []
    query = build_query(sorted(site_of), now, domains_of(sites))
    page = await reader.list_ids(query, max_results=LIST_MAX)
    emails: Counter[tuple[str, str]] = Counter()
    jobs: Counter[tuple[str, str]] = Counter()
    for message_id in page.ids[:LIST_MAX]:
        raw = await reader.get_raw(message_id)
        listed = raw.sender in site_of
        site = site_of[raw.sender] if listed else site_for_address(raw.sender, sites)
        shown = raw.sender if listed else (mask(raw.sender) or "(no sender)")
        if site is None:
            key = (shown, "not a job site")
        else:
            email, _flat = await asyncio.to_thread(
                read_email_flat, message_id, raw.sender, raw.received_at, raw.raw, site, listed
            )
            label = email.reader if email.outcome == "read" and email.reader else None
            key = (shown, label or _READER_OF_OUTCOME.get(email.outcome, "AI needed"))
            jobs[key] += len(email.jobs)
        emails[key] += 1
    return [CountRow(s, r, n, jobs[(s, r)]) for (s, r), n in sorted(emails.items())]


def render_counts(rows: list[CountRow]) -> list[str]:
    if not rows:
        return ["No email from your job sites in the last 24 hours."]
    width = max(len(row.sender) for row in rows)
    lines = [f"{'Sender':<{width}}  {'Reader':<14}  Emails  Jobs"]
    lines += [f"{r.sender:<{width}}  {r.reader:<14}  {r.emails:>6}  {r.jobs:>4}" for r in rows]
    lines.append(
        f"{'Total':<{width}}  {'':<14}  {sum(r.emails for r in rows):>6}"
        f"  {sum(r.jobs for r in rows):>4}"
    )
    return lines


async def _main() -> int:
    from hiretitan.mail.infra.repos import SendersRepo
    from hiretitan.mail_wiring import build_reader
    from hiretitan.platform.clock import SystemClock
    from hiretitan.platform.config.settings import get_settings
    from hiretitan.platform.db import create_engine, session_factory

    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        sessions = session_factory(engine)
        async with sessions() as session:
            senders = [s for s in await SendersRepo(session).list_all() if s.enabled]
        site_of = {s.address: s.site for s in senders}
        sites = frozenset(s.site for s in senders if s.built_in)

        async def no_event(_name: str, _data: dict[str, object]) -> None:
            return None

        reader = build_reader(settings, sessions, no_event)
        rows = await count_alerts(reader, site_of, sites, SystemClock().now())
        for line in render_counts(rows):
            print(line)
    finally:
        await engine.dispose()
    return 0


def main() -> None:
    if sys.platform == "win32":
        sys.exit(asyncio.run(_main(), loop_factory=asyncio.SelectorEventLoop))
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
