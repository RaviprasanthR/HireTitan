"""The layout tool (2026-11-22): masked alert skeletons, nothing stored, no word shown."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.infra.fake_gmail import FakeGmail
from hiretitan.mail.infra.models import MailReadMessageRow
from hiretitan.mail_shape import _parse, print_shapes
from hiretitan.mail_wiring import seed_mail_senders
from hiretitan.search.infra.models import JobRow

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mail"
SEED = Path(__file__).resolve().parents[3] / "seed" / "mail_senders.yaml"
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


def mailbox(tmp_path: Path, *names: str) -> FakeGmail:
    folder = tmp_path / "gmail"
    (folder / "messages").mkdir(parents=True)
    (folder / "profile.json").write_text(json.dumps({"address": "me@example.invalid"}), "utf-8")
    for name in names:
        shutil.copy(FIXTURES / "eml" / f"{name}.eml", folder / "messages" / f"{name}.eml")
    return FakeGmail(folder)


async def run(
    sessions: async_sessionmaker[AsyncSession], reader: FakeGmail, **options: object
) -> str:
    lines: list[str] = []
    settings: dict[str, object] = {"days": 7, "limit": 3, "site": None} | options
    await print_shapes(reader, sessions, NOW, write=lines.append, **settings)  # type: ignore[arg-type]
    return "\n".join(lines)


async def test_a_skeleton_shows_the_layout_and_what_the_reader_took(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await seed_mail_senders(sessions, SEED)

    out = await run(sessions, mailbox(tmp_path, "linkedin-01"))

    assert "Gmail lists 1 emails from your job sites in the last 7 days." in out
    assert "=== email 1: from jobalerts-noreply@linkedin.com · site linkedin" in out
    assert "https://www.linkedin.com/" in out
    assert out.count("job ") >= 3  # linkedin-01 has three jobs
    assert "title=L" in out


async def test_no_word_of_any_alert_reaches_the_output(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await seed_mail_senders(sessions, SEED)
    names = ["linkedin-01", "naukri-01", "indeed-01"]

    out = (await run(sessions, mailbox(tmp_path, *names), limit=10)).casefold()

    expected = yaml.safe_load((FIXTURES / "expected.yaml").read_text("utf-8"))["emails"]
    for name in names:
        for job in expected[f"{name}.eml"]["jobs"]:
            for value in (job["title"], job["company"], job["location"]):
                if value:
                    assert value.casefold() not in out, value


async def test_it_stores_nothing_and_marks_nothing_read(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await seed_mail_senders(sessions, SEED)

    await run(sessions, mailbox(tmp_path, "linkedin-01", "naukri-01"))

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MailReadMessageRow)) == 0
        assert await session.scalar(select(func.count()).select_from(JobRow)) == 0


async def test_one_site_only_and_the_limit(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    await seed_mail_senders(sessions, SEED)
    reader = mailbox(tmp_path, "linkedin-01", "linkedin-02", "naukri-01")

    out = await run(sessions, reader, site="naukri")
    assert "site naukri" in out
    assert "site linkedin" not in out

    out = await run(sessions, reader, limit=1)
    assert out.count("=== email") == 1


def test_the_options_are_bounded() -> None:
    assert _parse([]).days == 7
    for bad in (["--days", "0"], ["--days", "15"], ["--limit", "11"]):
        try:
            _parse(bad)
        except SystemExit:
            continue
        raise AssertionError(bad)
