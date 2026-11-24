"""Read-only Gmail over HTTP (research R1, R2): ``GET`` on three paths and nothing else.

This slice holds the profile call; the message list and fetch arrive with the alert reader. There
is no call here that sends, drafts, labels, trashes or changes mail, and no path outside
``users/me/profile``, ``users/me/messages`` and ``users/me/messages/{id}``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from typing import Any, Final

import httpx

from hiretitan.mail.application.ports import (
    GoogleAuth,
    MailAccessEndedError,
    MailMessageNotFoundError,
    MailUnavailableError,
    MessagePage,
    RawMessage,
    SecretsFileError,
    SecretsStore,
)
from hiretitan.mail.domain.mime import MAX_RAW_BYTES, UnreadableMessageError
from hiretitan.mail.domain.senders import address_from_header, is_sender_query
from hiretitan.mail.infra.retry import with_retries
from hiretitan.platform.security.outbound_allowlist import allowed_base_url

TIMEOUT_SECONDS: Final = 30.0
NETWORK_ERRORS: Final = (httpx.RequestError,)
_MESSAGE_ID: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")
MAX_LIST_PAGE: Final = 100
ACCESS_ENDED_MESSAGE: Final = "Gmail access has ended. Connect again."
Sleep = Callable[[float], Awaitable[None]]


async def _get(
    path: str, access_token: str, sleep: Sleep, params: dict[str, str] | None = None
) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=allowed_base_url("gmail.googleapis.com", "/gmail/v1"), timeout=TIMEOUT_SECONDS
        ) as client:
            return await client.get(
                path, params=params, headers={"Authorization": f"Bearer {access_token}"}
            )

    return await with_retries(send, sleep, NETWORK_ERRORS)


def _address(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
        address = body["emailAddress"]
    except (ValueError, KeyError, TypeError):
        raise MailUnavailableError("Gmail gave an answer that could not be read.") from None
    if not isinstance(address, str) or not address:
        raise MailUnavailableError("Gmail gave an answer that could not be read.")
    return address


class GmailProfile:
    """The mailbox address for an access token just granted (used once, when connecting)."""

    def __init__(self, *, sleep: Sleep = asyncio.sleep) -> None:
        self._sleep = sleep

    async def address_for(self, access_token: str) -> str:
        response = await _get("/users/me/profile", access_token, self._sleep)
        if response.status_code in (401, 403):
            raise MailAccessEndedError("Gmail did not accept the new access.")
        if response.status_code != 200:
            raise MailUnavailableError("Gmail did not answer the profile request.")
        return _address(response)


class GmailClient:
    """Reads the person's mailbox with their saved refresh token. A 401 is answered by one refresh
    and one retry; a second one ends the access (FR-005) and ``on_access_ended`` is told."""

    def __init__(
        self,
        *,
        auth: GoogleAuth,
        secrets: SecretsStore,
        on_access_ended: Callable[[str], Awaitable[None]],
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._auth = auth
        self._secrets = secrets
        self._on_access_ended = on_access_ended
        self._sleep = sleep
        self._access_token: str | None = None

    async def _end_access(self) -> MailAccessEndedError:
        self._access_token = None
        await self._on_access_ended(ACCESS_ENDED_MESSAGE)
        return MailAccessEndedError(ACCESS_ENDED_MESSAGE)

    async def _token(self, *, fresh: bool = False) -> str:
        if self._access_token is not None and not fresh:
            return self._access_token
        try:
            known = await asyncio.to_thread(self._secrets.read)
        except SecretsFileError:
            raise await self._end_access() from None
        if not (known.client_id and known.client_secret and known.refresh_token):
            raise await self._end_access()
        try:
            self._access_token = await self._auth.refresh(
                client_id=known.client_id,
                client_secret=known.client_secret,
                refresh_token=known.refresh_token,
            )
        except MailAccessEndedError:
            raise await self._end_access() from None
        return self._access_token

    async def _read(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        response = await _get(path, await self._token(), self._sleep, params)
        if response.status_code == 401:
            response = await _get(path, await self._token(fresh=True), self._sleep, params)
        if response.status_code == 401 or (
            response.status_code == 403 and not _is_rate_limit(response)
        ):
            raise await self._end_access()
        if response.status_code == 403:
            raise MailUnavailableError("Gmail is limiting requests right now.")
        return response

    async def profile(self) -> str:
        response = await self._read("/users/me/profile")
        if response.status_code != 200:
            raise MailUnavailableError("Gmail did not answer the profile request.")
        return _address(response)

    async def list_ids(
        self, query: str, *, page_token: str | None = None, max_results: int = 100
    ) -> MessagePage:
        """Message ids matching the sender query, newest first. The query must be exactly what
        ``build_query`` makes; anything else is refused before a request is made (FR-009)."""
        if not is_sender_query(query):
            raise ValueError("The query is not a sender query.")
        params = {"q": query, "maxResults": str(max(1, min(max_results, MAX_LIST_PAGE)))}
        if page_token:
            params["pageToken"] = page_token
        response = await self._read("/users/me/messages", params)
        if response.status_code != 200:
            raise MailUnavailableError("Gmail did not answer the list request.")
        body = _json(response)
        found = body.get("messages")
        ids = [
            item["id"]
            for item in (found if isinstance(found, list) else [])
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and _MESSAGE_ID.fullmatch(item["id"])
        ]
        token = body.get("nextPageToken")
        return MessagePage(ids, token if isinstance(token, str) and token else None)

    async def get_raw(self, message_id: str) -> RawMessage:
        """One message as RFC 5322 bytes, with Gmail's received time (``format=raw``)."""
        if not _MESSAGE_ID.fullmatch(message_id):
            raise ValueError(f"Not a message id: {message_id!r}")
        response = await self._read(f"/users/me/messages/{message_id}", {"format": "raw"})
        if response.status_code == 404:
            raise MailMessageNotFoundError(message_id)
        if response.status_code != 200:
            raise MailUnavailableError("Gmail did not answer the message request.")
        body = _json(response)
        size = body.get("sizeEstimate")
        if isinstance(size, int) and size > MAX_RAW_BYTES:
            raise UnreadableMessageError("The email is larger than 2 MB.")
        encoded, internal = body.get("raw"), body.get("internalDate")
        if not isinstance(encoded, str) or not isinstance(internal, str) or not internal.isdigit():
            raise MailUnavailableError("Gmail gave a message that could not be read.")
        if len(encoded) > MAX_RAW_BYTES * 4 // 3 + 8:
            raise UnreadableMessageError("The email is larger than 2 MB.")
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (binascii.Error, ValueError):
            raise MailUnavailableError("Gmail gave a message that could not be read.") from None
        try:
            headers = BytesParser(policy=policy.default).parsebytes(raw, headersonly=True)
            sender = address_from_header(str(headers.get("From", "")))
        except Exception:  # a hostile header must not stop the check; no sender means unreadable
            sender = ""
        received = datetime.fromtimestamp(int(internal) / 1000, UTC)
        return RawMessage(message_id, received, sender, raw)


_RATE_LIMIT_REASONS: Final = frozenset(
    {"ratelimitexceeded", "userratelimitexceeded", "dailylimitexceeded", "quotaexceeded"}
)


def _is_rate_limit(response: httpx.Response) -> bool:
    """Gmail answers 403 both for a missing permission and for "slow down": only the first one
    means the person's access has ended."""
    error = _json(response).get("error")
    if not isinstance(error, dict):
        return False
    items = error.get("errors")
    if not isinstance(items, list):
        return False
    return any(
        isinstance(item, dict) and str(item.get("reason", "")).lower() in _RATE_LIMIT_REASONS
        for item in items
    )


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
