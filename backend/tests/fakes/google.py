"""A scripted Google for the connection tests: records every call, answers what a test sets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import urlencode

from hiretitan.mail.application.ports import (
    MailAccessEndedError,
    MailUnavailableError,
    TokenGrant,
)
from hiretitan.mail.domain.oauth import READONLY_SCOPE

ACCESS = "ya29.synthetic-access-token-0001"
REFRESH = "1//0g-synthetic-refresh-token-0002"


@dataclass
class FakeGoogle:
    address: str = "jobseeker@example.invalid"
    scope: str = READONLY_SCOPE
    refresh_token: str | None = REFRESH
    exchange_fails: bool = False
    revoke_fails: bool = False
    calls: list[str] = field(default_factory=list)
    revoked: list[str] = field(default_factory=list)
    exchanged: list[dict[str, str]] = field(default_factory=list)
    hold_profile: asyncio.Event | None = None  # a test holds the sign-in open at the profile call
    profile_started: asyncio.Event = field(default_factory=asyncio.Event)

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str
    ) -> str:
        self.calls.append("authorize_url")
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "scope": READONLY_SCOPE,
            }
        )
        return f"https://accounts.example.invalid/auth?{query}"

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> TokenGrant:
        self.calls.append("exchange_code")
        self.exchanged.append({"code": code, "code_verifier": code_verifier})
        if self.exchange_fails:
            raise MailAccessEndedError("invalid_grant")
        return TokenGrant(ACCESS, self.refresh_token, self.scope)

    async def refresh(self, *, client_id: str, client_secret: str, refresh_token: str) -> str:
        self.calls.append("refresh")
        return ACCESS

    async def revoke(self, token: str) -> None:
        self.calls.append("revoke")
        if self.revoke_fails:
            raise MailUnavailableError("google is down")
        self.revoked.append(token)

    async def address_for(self, access_token: str) -> str:
        self.calls.append("profile")
        self.profile_started.set()
        if self.hold_profile is not None:
            await self.hold_profile.wait()
        return self.address
