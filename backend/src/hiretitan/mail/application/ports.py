"""The boundaries of the mail module (constitution VI): the mail provider, the secrets store and
the hand-over of alert jobs to the search module. ``hiretitan/mail_wiring.py`` implements the last
one, so ``mail`` never imports ``search`` and a later mail feature can reuse the connection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
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
