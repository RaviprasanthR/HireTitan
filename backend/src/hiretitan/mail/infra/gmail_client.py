"""Read-only Gmail over HTTP (research R1, R2): ``GET`` on three paths and nothing else.

This slice holds the profile call; the message list and fetch arrive with the alert reader. There
is no call here that sends, drafts, labels, trashes or changes mail, and no path outside
``users/me/profile``, ``users/me/messages`` and ``users/me/messages/{id}``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Final

import httpx

from hiretitan.mail.application.ports import (
    GoogleAuth,
    MailAccessEndedError,
    MailUnavailableError,
    SecretsFileError,
    SecretsStore,
)
from hiretitan.mail.infra.retry import with_retries
from hiretitan.platform.security.outbound_allowlist import allowed_base_url

TIMEOUT_SECONDS: Final = 30.0
NETWORK_ERRORS: Final = (httpx.RequestError,)
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
        if response.status_code in (401, 403):
            raise await self._end_access()
        return response

    async def profile(self) -> str:
        response = await self._read("/users/me/profile")
        if response.status_code != 200:
            raise MailUnavailableError("Gmail did not answer the profile request.")
        return _address(response)
