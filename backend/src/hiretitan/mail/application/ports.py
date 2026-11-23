"""The boundaries of the mail module (constitution VI): the mail provider, the secrets store and
the hand-over of alert jobs to the search module. ``hiretitan/mail_wiring.py`` implements the last
one, so ``mail`` never imports ``search`` and a later mail feature can reuse the connection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from hiretitan.mail.domain.alerts import AlertJob


class MailAccessEndedError(Exception):
    """The access no longer works: expired, revoked or the wrong credentials (FR-005)."""


class MailUnavailableError(Exception):
    """The mail provider did not answer, after the retries (a network or Google problem)."""


class MailMessageNotFoundError(Exception):
    """The message is gone (deleted since it was listed)."""


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


class CheckAbandonedError(Exception):
    """The connection, the run or its rules went away while a check was reading (Disconnect or
    Delete all): nothing more may be stored and the check stops."""


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


@dataclass(frozen=True, slots=True)
class ReadEmail:
    """One email a check read, with what it yielded. The body is never part of this (FR-016)."""

    message_id: str
    sender: str
    received_at: datetime
    outcome: str  # read | no_jobs | unreadable | needs_ai
    reader: str | None
    jobs: list[AlertJob]
    injection_signals: list[dict[str, Any]]


class AlertBatchSink(Protocol):
    """Records a batch of read emails and hands their jobs to the search module (rules,
    deduplication, Explore), all in one transaction: an email is never marked read without its
    jobs being stored, and the other way round (FR-011)."""

    async def store(
        self,
        *,
        search_run_id: UUID,
        mail_check_id: UUID,
        batch_no: int,
        emails: Sequence[ReadEmail],
        now: datetime,
    ) -> SinkCounts: ...


@dataclass(frozen=True, slots=True)
class StartedCheck:
    search_run_id: UUID
    mail_check_id: UUID
    window_start: datetime


class CheckNotReadyError(Exception):
    """A check cannot start: ``reason`` is ``not_connected``, ``needs_reconnect``,
    ``search_running`` or ``no_rules``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CheckRuns(Protocol):
    """A mail check is a search run (research R8); this is how the mail module reaches it."""

    async def start(self, *, trigger: str, now: datetime, reread: bool = False) -> StartedCheck:
        """Create the run and its check record and queue it. ``CheckNotReadyError`` when not
        connected, access ended, another search runs, or the rules are not approved. ``reread``
        forgets which emails of the check's window were read, in the same transaction (FR-013e)."""
        ...

    async def locate(self, workflow_run_id: UUID) -> StartedCheck | None:
        """The check a queued workflow run belongs to."""
        ...

    async def stop_requested(self, search_run_id: UUID) -> bool: ...

    async def finish(
        self, search_run_id: UUID, *, outcome: str, message: str | None, now: datetime
    ) -> None: ...


class SecretsFileError(RuntimeError):
    """The secrets file cannot be trusted: damaged, or readable by other people."""


class CredentialsFromEnvironmentError(ValueError):
    """The client id and secret come from the environment, so they cannot be saved here."""


@dataclass(frozen=True, slots=True)
class GoogleSecrets:
    """What is known. The values stay out of ``repr`` so a stray log line cannot show them."""

    client_id: str | None = field(default=None, repr=False)
    client_secret: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)


class SecretsStore(Protocol):
    """The Google client credentials and the refresh token; never shown, logged or sent on."""

    @property
    def credentials_from_environment(self) -> bool: ...

    def read(self) -> GoogleSecrets: ...

    def save_credentials(self, client_id: str, client_secret: str) -> None: ...

    def save_refresh_token(self, token: str) -> None: ...

    def clear_token(self) -> None: ...

    def clear_all(self) -> None: ...


@dataclass(frozen=True, slots=True)
class TokenGrant:
    """Google's answer to a code exchange. The tokens stay out of ``repr``."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    scope: str


class GoogleAuth(Protocol):
    """Google's sign-in for the person's own OAuth client (research R1)."""

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str
    ) -> str: ...

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> TokenGrant:
        """Raises ``MailAccessEndedError`` when Google refuses the code, ``MailUnavailableError``
        when it cannot be reached."""
        ...

    async def refresh(self, *, client_id: str, client_secret: str, refresh_token: str) -> str:
        """A fresh access token. ``MailAccessEndedError`` on ``invalid_grant`` (FR-005)."""
        ...

    async def revoke(self, token: str) -> None:
        """Hand the token back to Google. ``MailUnavailableError`` when it cannot be reached."""
        ...


class MailboxProfile(Protocol):
    async def address_for(self, access_token: str) -> str:
        """The mailbox's address (``users/me/profile``)."""
        ...


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    state: str
    address: str
    last_check_started_at: datetime | None
    last_error: str | None


class MailStore(Protocol):
    """The connection row and the records kept about mail read. Each call is its own transaction."""

    async def connection(self) -> ConnectionRecord | None: ...

    async def connect(self, address: str, now: datetime) -> None: ...

    async def set_state(self, state: str, error: str | None) -> None: ...

    async def erase_all(self) -> None:
        """Remove the connection and the records of email read and of checks (Disconnect)."""
        ...
