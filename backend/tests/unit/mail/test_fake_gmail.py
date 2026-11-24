"""The scripted mailbox (T011): the e2e stack and the workflow tests read mail through it."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hiretitan.mail.infra.fake_gmail import FakeGmail

EML = Path(__file__).resolve().parents[2] / "fixtures" / "mail" / "eml"


@pytest.fixture
def mailbox(tmp_path: Path) -> Path:
    (tmp_path / "messages").mkdir()
    (tmp_path / "profile.json").write_text(
        json.dumps({"address": "jobseeker@example.invalid"}), encoding="utf-8"
    )
    for name in ("linkedin-01", "naukri-01", "naukri-02", "indeed-01", "unknown-01"):
        shutil.copy(EML / f"{name}.eml", tmp_path / "messages" / f"{name}.eml")
    return tmp_path


def epoch(moment: datetime) -> int:
    return int(moment.timestamp())


async def test_US1_AS2_profile_gives_the_address(mailbox: Path) -> None:
    assert await FakeGmail(mailbox).profile() == "jobseeker@example.invalid"


async def test_FR009_only_the_listed_senders_are_returned(mailbox: Path) -> None:
    reader = FakeGmail(mailbox)
    query = "from:(naukrialerts@naukri.com OR alert@indeed.com) after:0"

    page = await reader.list_ids(query)

    assert sorted(page.ids) == ["indeed-01", "naukri-01", "naukri-02"]
    assert page.next_page_token is None


async def test_FR011_only_mail_after_the_cutoff_is_returned(mailbox: Path) -> None:
    reader = FakeGmail(mailbox)
    everything = await reader.list_ids("from:(naukrialerts@naukri.com) after:0")
    first = await reader.get_raw(everything.ids[-1])  # the oldest
    cutoff = epoch(first.received_at) + 1

    newer = await reader.list_ids(f"from:(naukrialerts@naukri.com) after:{cutoff}")

    assert first.id not in newer.ids
    assert len(newer.ids) == len(everything.ids) - 1


async def test_FR009_results_are_newest_first_and_paged(mailbox: Path) -> None:
    reader = FakeGmail(mailbox)
    query = "from:(naukrialerts@naukri.com OR alert@indeed.com) after:0"

    first = await reader.list_ids(query, max_results=2)
    second = await reader.list_ids(query, max_results=2, page_token=first.next_page_token)

    assert len(first.ids) == 2
    assert first.next_page_token is not None
    assert len(second.ids) == 1
    assert second.next_page_token is None
    dates = [(await reader.get_raw(i)).received_at for i in [*first.ids, *second.ids]]
    assert dates == sorted(dates, reverse=True)


async def test_FR013_a_message_comes_back_whole_with_its_sender_and_time(mailbox: Path) -> None:
    message = await FakeGmail(mailbox).get_raw("naukri-01")

    assert message.id == "naukri-01"
    assert message.sender == "naukrialerts@naukri.com"
    assert message.received_at.tzinfo is not None
    assert message.received_at < datetime(2026, 11, 18, tzinfo=UTC)
    assert b"Subject:" in message.raw
    assert (mailbox / "messages" / "naukri-01.eml").read_bytes() == message.raw


@pytest.mark.parametrize(
    "query",
    [
        "backend engineer",  # free text is never asked for (FR-009)
        "from:(a@x.example.invalid) after:0 label:inbox",
        "after:0",  # no senders at all
        "from:() after:0",
    ],
)
async def test_FR009_a_query_that_is_not_senders_and_time_is_refused(
    mailbox: Path, query: str
) -> None:
    with pytest.raises(ValueError):
        await FakeGmail(mailbox).list_ids(query)


async def _no_publish(name: str, data: dict[str, object]) -> None:
    return None


def test_FR001_wiring_picks_the_scripted_mailbox_when_asked(mailbox: Path) -> None:
    from hiretitan.mail_wiring import build_reader
    from hiretitan.platform.config.settings import Settings

    reader = build_reader(
        Settings(_env_file=None, HIRETITAN_MAIL="fake", HIRETITAN_FAKE_GMAIL_DIR=str(mailbox)),  # type: ignore[call-arg]
        None,  # type: ignore[arg-type]  (a scripted mailbox never touches the database)
        _no_publish,
    )

    assert isinstance(reader, FakeGmail)


def test_FR001_a_scripted_mailbox_needs_its_folder() -> None:
    from hiretitan.mail_wiring import build_reader
    from hiretitan.platform.config.settings import Settings

    with pytest.raises(ValueError, match="HIRETITAN_FAKE_GMAIL_DIR"):
        build_reader(
            Settings(_env_file=None, HIRETITAN_MAIL="fake"),  # type: ignore[call-arg]
            None,  # type: ignore[arg-type]
            _no_publish,
        )


@pytest.mark.parametrize("message_id", ["../profile", "..\\x", "a/b", "", "a.b", "x y"])
async def test_FR009_a_message_id_cannot_reach_outside_the_messages_folder(
    tmp_path: Path, message_id: str
) -> None:
    (tmp_path / "messages").mkdir()
    (tmp_path / "profile.json").write_text('{"address": "p@example.invalid"}', "utf-8")

    with pytest.raises(ValueError, match="message id"):
        await FakeGmail(tmp_path).get_raw(message_id)
