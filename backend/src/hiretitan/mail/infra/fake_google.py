"""A scripted Google for ``HIRETITAN_MAIL=fake`` (the e2e stack and demos): no network at all.

The consent "page" is the app's own callback, so pressing Connect comes straight back as if the
person had agreed. The mailbox address is the one in the fake Gmail folder's ``profile.json``.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from hiretitan.mail.application.ports import TokenGrant
from hiretitan.mail.domain.oauth import READONLY_SCOPE
from hiretitan.mail.infra.fake_gmail import FakeGmail

FAKE_REFRESH_TOKEN = "1//fake-refresh-token-for-the-demo-stack"  # noqa: S105
FAKE_ACCESS_TOKEN = "ya29.fake-access-token-for-the-demo-stack"  # noqa: S105


class FakeGoogle:
    def __init__(self, folder: Path) -> None:
        self._mailbox = FakeGmail(folder)

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str
    ) -> str:
        return f"{redirect_uri}?{urlencode({'code': 'fake-code', 'state': state})}"

    async def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
        code_verifier: str,
    ) -> TokenGrant:
        return TokenGrant(FAKE_ACCESS_TOKEN, FAKE_REFRESH_TOKEN, READONLY_SCOPE)

    async def refresh(self, *, client_id: str, client_secret: str, refresh_token: str) -> str:
        return FAKE_ACCESS_TOKEN

    async def revoke(self, token: str) -> None:
        return None

    async def address_for(self, access_token: str) -> str:
        return await self._mailbox.profile()
