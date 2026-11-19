"""Composition root for mail (feature 002c): where ``hiretitan.mail`` meets the rest of the app."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.connection import ConnectionService, Publish
from hiretitan.mail.application.consents import PendingConsents
from hiretitan.mail.application.ports import GoogleAuth, MailboxProfile, MailReader
from hiretitan.mail.infra.fake_gmail import FakeGmail
from hiretitan.mail.infra.fake_google import FakeGoogle
from hiretitan.mail.infra.gmail_client import GmailProfile
from hiretitan.mail.infra.google_oauth import GoogleOAuth
from hiretitan.mail.infra.repos import SendersRepo
from hiretitan.mail.infra.secrets_file import SecretsFile
from hiretitan.mail.infra.seed import load_seed
from hiretitan.mail.infra.store import SqlMailStore
from hiretitan.platform.clock import ClockPort
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
    raise NotImplementedError("Reading messages from Gmail arrives with the alert reader (US2).")


async def _nothing_to_stop() -> None:
    """No mail check exists yet to stop; the check task replaces this when it arrives (US2)."""


def build_connection_service(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    clock: ClockPort,
    publish: Publish,
) -> ConnectionService:
    """The connection use cases over real Google, or the scripted one (``HIRETITAN_MAIL=fake``)."""
    auth: GoogleAuth
    profile: MailboxProfile
    if settings.mail == "fake":
        if settings.fake_gmail_dir is None:
            raise ValueError("HIRETITAN_MAIL=fake needs HIRETITAN_FAKE_GMAIL_DIR.")
        fake = FakeGoogle(settings.fake_gmail_dir)
        auth, profile = fake, fake
    else:
        auth, profile = GoogleOAuth(), GmailProfile()
    return ConnectionService(
        store=SqlMailStore(sessions),
        secrets=SecretsFile(settings.data_dir / "secrets" / "gmail.json", os.environ),
        auth=auth,
        profile=profile,
        consents=PendingConsents(clock),
        clock=clock,
        redirect_uri=f"http://localhost:{settings.port}/api/v1/mail/google/callback",
        stop_check=_nothing_to_stop,
        publish=publish,
    )
