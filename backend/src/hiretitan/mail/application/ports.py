"""The boundaries of the mail module (constitution VI): the mail provider, the secrets store and
the hand-over of alert jobs to the search module. ``hiretitan/mail_wiring.py`` implements the last
one, so ``mail`` never imports ``search`` and a later mail feature can reuse the connection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from hiretitan.mail.domain.alerts import AlertJob


class MailAccessEndedError(Exception):
    """The access no longer works: expired, revoked or the wrong credentials (FR-005)."""


class MailUnavailableError(Exception):
    """The mail provider did not answer, after the retries (a network or Google problem)."""


@dataclass(frozen=True, slots=True)
class MessagePage:
    ids: list[str]
    next_page_token: str | None


@dataclass(frozen=True, slots=True)
class RawMessage:
    id: str
    received_at: datetime
    sender: str
    raw: bytes


class MailReader(Protocol):
    """Read-only access to one mailbox. There is no call that sends, drafts or changes mail."""

    async def profile(self) -> str:
        """The mailbox's address."""
        ...

    async def list_ids(
        self, query: str, *, page_token: str | None = None, max_results: int = 100
    ) -> MessagePage:
        """Message ids matching a search query, newest first."""
        ...

    async def get_raw(self, message_id: str) -> RawMessage:
        """One message in full (RFC 5322 bytes), plus Gmail's received time."""
        ...


@dataclass(frozen=True, slots=True)
class SinkCounts:
    """What the search module did with a batch of alert jobs (FR-026: they add up)."""

    new: int = 0
    already_known: int = 0
    left_out: int = 0
    already_in_pipeline: int = 0
    possible_duplicates: int = 0
    in_pipeline_titles: tuple[str, ...] = ()

    @property
    def found(self) -> int:
        return self.new + self.already_known + self.left_out + self.already_in_pipeline


class AlertJobsSink(Protocol):
    """Hands alert jobs to the search module: rules, deduplication, Explore."""

    async def store(
        self,
        search_run_id: UUID,
        message_id: UUID | None,
        jobs: Sequence[AlertJob],
        now: datetime,
    ) -> SinkCounts: ...


class SecretsStore(Protocol):
    """The Google client credentials and the refresh token; never shown, logged or sent on."""

    def has_credentials(self) -> bool: ...

    def has_token(self) -> bool: ...
