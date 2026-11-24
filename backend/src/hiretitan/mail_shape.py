"""Print the masked layout of recent job-alert emails: ``python -m hiretitan.mail_shape``.

For fixing a site's reader against real alerts without sharing them (2026-11-22). Run it where
HireTitan runs, with Gmail connected:

    docker compose exec worker python -m hiretitan.mail_shape --days 7 --limit 3

It asks Gmail for the enabled senders and site domains (the same query a check sends, looking
back ``--days``), opens at most ``--limit`` emails, and prints each one's skeleton: every letter
masked, digits as 9, line order and link shapes kept, and which lines the site's reader took a
job's title, company and place from. It stores nothing, marks nothing read and calls no AI.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.ports import MailReader
from hiretitan.mail.domain.mime import UnreadableMessageError, flatten_message
from hiretitan.mail.domain.readers import read_alert
from hiretitan.mail.domain.senders import build_query, domains_of, site_for_address
from hiretitan.mail.domain.skeleton import mask, skeleton
from hiretitan.mail.infra.repos import SendersRepo
from hiretitan.platform.clock import SystemClock

DAYS_MAX = 14
LIMIT_MAX = 10


def _shown_sender(sender: str, site: str | None) -> str:
    """A job site's own address is public and kept; any other address is masked."""
    return sender if site is not None else mask(sender)


async def print_shapes(
    reader: MailReader,
    sessions: async_sessionmaker[AsyncSession],
    now: datetime,
    *,
    days: int,
    limit: int,
    site: str | None,
    write: Callable[[str], object],
) -> int:
    """Print the skeletons; returns how many emails were shown."""
    async with sessions() as session:
        senders = [s for s in await SendersRepo(session).list_all() if s.enabled]
    site_of = {s.address: s.site for s in senders}
    sites = frozenset(s.site for s in senders if s.built_in)
    if not site_of:
        write("No sender is switched on.")
        return 0
    query = build_query(sorted(site_of), now, domains_of(sites), timedelta(days=days))
    page = await reader.list_ids(query, max_results=100)
    write(f"Gmail lists {len(page.ids)} emails from your job sites in the last {days} days.")
    shown = 0
    for message_id in page.ids:
        if shown >= limit:
            break
        raw = await reader.get_raw(message_id)
        email_site = site_of.get(raw.sender) or site_for_address(raw.sender, sites)
        if site is not None and email_site != site:
            continue
        shown += 1
        write("")
        write(
            f"=== email {shown}: from {_shown_sender(raw.sender, email_site)}"
            f" · site {email_site or 'none'} · received {raw.received_at:%Y-%m-%d %H:%M}"
        )
        try:
            flat = flatten_message(raw.raw)
        except UnreadableMessageError:
            write("could not be read (not a mail HireTitan can open)")
            continue
        jobs = read_alert(email_site, flat, raw.received_at) if email_site else []
        for line in skeleton(flat, jobs):
            write(line)
    if shown == 0:
        write("No email to show.")
    return shown


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--days", type=int, default=7, help=f"look back 1 to {DAYS_MAX} days")
    parser.add_argument("--limit", type=int, default=3, help=f"show 1 to {LIMIT_MAX} emails")
    parser.add_argument("--site", default=None, help="only this site (linkedin, naukri, ...)")
    args = parser.parse_args(argv)
    if not 1 <= args.days <= DAYS_MAX or not 1 <= args.limit <= LIMIT_MAX:
        parser.error(f"--days must be 1 to {DAYS_MAX} and --limit 1 to {LIMIT_MAX}")
    return args


async def _main(argv: list[str]) -> int:
    from hiretitan.mail_wiring import build_reader
    from hiretitan.platform.config.settings import get_settings
    from hiretitan.platform.db import create_engine, session_factory

    args = _parse(argv)
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:

        async def no_event(_name: str, _data: dict[str, object]) -> None:
            return None

        reader = build_reader(settings, session_factory(engine), no_event)
        await print_shapes(
            reader,
            session_factory(engine),
            SystemClock().now(),
            days=args.days,
            limit=args.limit,
            site=args.site,
            write=print,
        )
    finally:
        await engine.dispose()
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if sys.platform == "win32":
        sys.exit(asyncio.run(_main(argv), loop_factory=asyncio.SelectorEventLoop))
    sys.exit(asyncio.run(_main(argv)))


if __name__ == "__main__":
    main()
