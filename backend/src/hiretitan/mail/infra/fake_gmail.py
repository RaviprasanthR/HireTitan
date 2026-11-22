"""A scripted mailbox: ``HIRETITAN_MAIL=fake`` reads synthetic mail from a folder instead of Gmail.

The e2e stack and the workflow tests use it. The folder holds ``profile.json`` (``{"address":
…}``) and ``messages/<id>.eml``. It understands only the query the real reader sends, senders and
a time (``from:(a OR b) after:<epoch>``), and refuses anything else, so a test fails if the code
ever asks for more than that (FR-009). It sends nothing and changes nothing.
"""

from __future__ import annotations

import asyncio
import json
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from hiretitan.mail.application.ports import MessagePage, RawMessage
from hiretitan.mail.domain.senders import address_from_header

_FROM = re.compile(r"from:\(([^)]*)\)")
_AFTER = re.compile(r"after:(\d+)")
_MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]+")


def parse_query(query: str) -> tuple[list[str], int]:
    """The senders and the cutoff in a query, or ``ValueError`` if it asks for anything else."""
    senders_match = _FROM.search(query)
    after_match = _AFTER.search(query)
    if senders_match is None or after_match is None:
        raise ValueError("The query must be from:(…) and after:<time>.")
    rest = _AFTER.sub("", _FROM.sub("", query)).strip()
    if rest:
        raise ValueError(f"The query asks for more than senders and a time: {rest!r}")
    senders = [part.strip().lower() for part in senders_match.group(1).split(" OR ")]
    if not senders or not all(senders):
        raise ValueError("The query names no sender.")
    return senders, int(after_match.group(1))


class FakeGmail:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def _read(self, message_id: str) -> RawMessage:
        # Gmail ids are plain; never build a path from anything more
        if not _MESSAGE_ID.fullmatch(message_id):
            raise ValueError(f"Not a message id: {message_id!r}")
        raw = (self._folder / "messages" / f"{message_id}.eml").read_bytes()
        message = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
        sender = address_from_header(str(message["From"]))
        return RawMessage(message_id, parsedate_to_datetime(str(message["Date"])), sender, raw)

    async def profile(self) -> str:
        data = json.loads(
            await asyncio.to_thread((self._folder / "profile.json").read_text, "utf-8")
        )
        return str(data["address"])

    async def list_ids(
        self, query: str, *, page_token: str | None = None, max_results: int = 100
    ) -> MessagePage:
        senders, after = parse_query(query)
        paths = await asyncio.to_thread(lambda: sorted((self._folder / "messages").glob("*.eml")))
        found = [m for m in (self._read(p.stem) for p in paths) if m.sender in senders]
        found = [m for m in found if m.received_at.timestamp() > after]
        found.sort(key=lambda m: (m.received_at, m.id), reverse=True)
        start = int(page_token or 0)
        page = found[start : start + max_results]
        more = start + max_results < len(found)
        return MessagePage([m.id for m in page], str(start + max_results) if more else None)

    async def get_raw(self, message_id: str) -> RawMessage:
        return await asyncio.to_thread(self._read, message_id)
