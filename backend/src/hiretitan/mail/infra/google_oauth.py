"""Google sign-in: the consent address, the code exchange, refresh and revoke (research R1).

The only module that talks to Google's sign-in host, and it only POSTs: ``/token`` and ``/revoke``.
Nothing here reads mail. Errors never carry a secret, a code or a Google answer's body.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Final

import httpx

from hiretitan.mail.application.ports import (
    MailAccessEndedError,
    MailUnavailableError,
    TokenGrant,
)
from hiretitan.mail.domain.oauth import build_authorize_url
from hiretitan.mail.infra.retry import with_retries
from hiretitan.platform.security.outbound_allowlist import allowed_base_url

TIMEOUT_SECONDS: Final = 20.0
NETWORK_ERRORS: Final = (httpx.RequestError,)


class GoogleOAuth:
    def __init__(self, *, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._sleep = sleep

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str
    ) -> str:
        return build_authorize_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            challenge=code_challenge,
        )

    async def _post(self, path: str, form: dict[str, str]) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                base_url=allowed_base_url("oauth2.googleapis.com", ""), timeout=TIMEOUT_SECONDS
            ) as client:
                return await client.post(path, data=form)

        return await with_retries(send, self._sleep, NETWORK_ERRORS)

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> TokenGrant:
        response = await self._post(
            "/token",
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        body = _json(response)
        access, scope = body.get("access_token"), body.get("scope")
        if response.status_code != 200 or not isinstance(access, str) or not isinstance(scope, str):
            raise MailAccessEndedError("Google did not accept the sign-in.")
        refresh = body.get("refresh_token")
        return TokenGrant(access, refresh if isinstance(refresh, str) else None, scope)

    async def refresh(self, *, client_id: str, client_secret: str, refresh_token: str) -> str:
        response = await self._post(
            "/token",
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        access = _json(response).get("access_token")
        if response.status_code != 200 or not isinstance(access, str):
            # invalid_grant (expired or revoked), invalid_client (wrong secret): the access is over
            raise MailAccessEndedError("Google no longer accepts the saved access.")
        return access

    async def revoke(self, token: str) -> None:
        response = await self._post("/revoke", {"token": token})
        # a 400 means Google no longer knows the token: it is already as revoked as it can be
        if response.status_code not in (200, 400):
            raise MailUnavailableError("Google did not confirm the revoke.")


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
