"""Composition root for mail (feature 002c): where ``hiretitan.mail`` meets the rest of the app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.ports import MailReader
from hiretitan.mail.infra.fake_gmail import FakeGmail
from hiretitan.mail.infra.repos import SendersRepo
from hiretitan.mail.infra.seed import load_seed
from hiretitan.platform.config.settings import Settings


async def seed_mail_senders(sessions: async_sessionmaker[AsyncSession], path: Path) -> int:
    """Load the shipped sender list at start-up; no file means nothing to load. Returns how many
    addresses were new. A bad file stops start-up, like the other shipped tables."""
    if not await asyncio.to_thread(path.exists):
        return 0
    seed = await asyncio.to_thread(load_seed, path)
    async with sessions() as session:
        added = await SendersRepo(session).merge_seed(seed)
        await session.commit()
        return added


def build_reader(settings: Settings) -> MailReader:
    """The mailbox the app reads: scripted synthetic mail for the e2e stack, else real Gmail."""
    if settings.mail == "fake":
        if settings.fake_gmail_dir is None:
            raise ValueError("HIRETITAN_MAIL=fake needs HIRETITAN_FAKE_GMAIL_DIR.")
        return FakeGmail(settings.fake_gmail_dir)
    raise NotImplementedError("The Gmail reader arrives with task T016.")
