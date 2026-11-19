"""Pure helpers for Google sign-in: the one scope HireTitan asks for, PKCE and the consent URL."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Final
from urllib.parse import urlencode

READONLY_SCOPE: Final = "https://www.googleapis.com/auth/gmail.readonly"
AUTHORIZE_ENDPOINT: Final = "https://accounts.google.com/o/oauth2/v2/auth"


def new_state() -> str:
    """An unguessable one-time value that ties Google's answer to the request that started it."""
    return secrets.token_urlsafe(32)


def new_verifier() -> str:
    """A PKCE code verifier (RFC 7636: 43 to 128 characters)."""
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    """The S256 challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def granted_only_readonly(scope: str | None) -> bool:
    """True only when the token's scope is exactly the read-only scope (FR-002)."""
    return set((scope or "").split()) == {READONLY_SCOPE}


def build_authorize_url(*, client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": READONLY_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return f"{AUTHORIZE_ENDPOINT}?{query}"
