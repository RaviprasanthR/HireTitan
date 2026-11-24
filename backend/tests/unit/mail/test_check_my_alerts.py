"""T047: counting a day's alerts per sender and reader, with no job field in the output."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from hiretitan.mail.application.ports import MessagePage, RawMessage
from hiretitan.mail_counts import count_alerts, render_counts

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mail"
EMAILS: dict[str, dict[str, Any]] = yaml.safe_load((FIXTURES / "expected.yaml").read_text("utf-8"))[
    "emails"
]
NAMES = ["linkedin-01.eml", "naukri-01.eml", "unknown-01.eml", "injection-02.eml"]


class ScriptedReader:
    """A mailbox holding a few fixture emails; it records the queries it is asked."""

    def __init__(self, names: list[str]) -> None:
        self.queries: list[str] = []
        self._messages = {
            name: RawMessage(
                name.removesuffix(".eml"),
                datetime.fromisoformat(EMAILS[name]["received"]),
                EMAILS[name]["sender"],
                (FIXTURES / "eml" / name).read_bytes(),
            )
            for name in names
        }

    async def profile(self) -> str:
        return "someone@example.invalid"

    async def list_ids(
        self, query: str, *, page_token: str | None = None, max_results: int = 100
    ) -> MessagePage:
        self.queries.append(query)
        return MessagePage([m.id for m in self._messages.values()], None)

    async def get_raw(self, message_id: str) -> RawMessage:
        return self._messages[f"{message_id}.eml"]


SITE_OF = {
    EMAILS["linkedin-01.eml"]["sender"]: "linkedin",
    EMAILS["naukri-01.eml"]["sender"]: "naukri",
}
NOW = datetime.fromisoformat(EMAILS["naukri-01.eml"]["received"]) + timedelta(hours=1)


async def test_FR011_counts_per_sender_and_reader_over_the_last_24_hours() -> None:
    reader = ScriptedReader(NAMES)

    rows = await count_alerts(reader, SITE_OF, frozenset(SITE_OF.values()), NOW)

    assert len(reader.queries) == 1
    assert reader.queries[0].startswith("from:(")
    by_reader = {row.reader: row for row in rows}
    linkedin = ("linkedin-01.eml", "injection-02.eml")  # the planted email is a LinkedIn alert
    assert by_reader["linkedin"].emails == 2
    assert by_reader["linkedin"].jobs == sum(len(EMAILS[n]["jobs"]) for n in linkedin)
    assert by_reader["naukri"].jobs == len(EMAILS["naukri-01.eml"]["jobs"])
    assert sum(row.emails for row in rows) == len(NAMES)


async def test_FR013_output_holds_no_title_company_or_link() -> None:
    rows = await count_alerts(ScriptedReader(NAMES), SITE_OF, frozenset(SITE_OF.values()), NOW)

    text = "\n".join(render_counts(rows))

    assert "http" not in text
    for name in NAMES:
        for job in [*(EMAILS[name].get("jobs") or []), *(EMAILS[name].get("ai_expected") or [])]:
            assert job["title"] not in text
            if job["company"]:
                assert job["company"] not in text
            if job["location"]:
                assert job["location"] not in text


async def test_an_address_that_is_not_a_listed_sender_is_masked() -> None:
    rows = await count_alerts(ScriptedReader(NAMES), SITE_OF, frozenset(SITE_OF.values()), NOW)

    text = "\n".join(render_counts(rows))

    for name in ("unknown-01.eml", "injection-02.eml"):
        sender = EMAILS[name]["sender"]
        if sender not in SITE_OF:
            assert sender not in text


async def test_no_sender_switched_on_lists_nothing() -> None:
    reader = ScriptedReader(NAMES)

    rows = await count_alerts(reader, {}, frozenset(), NOW)

    assert rows == []
    assert reader.queries == []
