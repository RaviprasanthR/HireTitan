"""Gmail profile contract (T013): US1 AS2, FR-005, SC-007. Provisional fixtures (see their README).

Only ``GET`` on ``users/me/profile``, ``users/me/messages`` and ``users/me/messages/{id}`` may
reach the Gmail host: a catch-all route fails the test on anything else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from hiretitan.mail.application.ports import (
    GoogleSecrets,
    MailAccessEndedError,
    MailUnavailableError,
)
from hiretitan.mail.infra.gmail_client import GmailClient, GmailProfile

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gmail"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ALLOWED_PATH = re.compile(r"^/gmail/v1/users/me/(profile|messages|messages/[A-Za-z0-9_-]+)$")


def fixture(name: str) -> dict[str, object]:
    data = json.loads((FIXTURES / name).read_text("utf-8"))
    assert isinstance(data, dict)
    return data


class Secrets:
    """Just enough of the secrets store for the client: it only reads."""

    credentials_from_environment = False

    def __init__(self, refresh_token: str | None = "1//the-refresh-token") -> None:
        self._refresh = refresh_token

    def read(self) -> GoogleSecrets:
        return GoogleSecrets("client-id-1234567890", "client-secret-1234567890", self._refresh)


async def no_wait(_seconds: float) -> None:
    return None


class Ended:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def __call__(self, message: str) -> None:
        self.messages.append(message)


def make_client(refresh_token: str | None = "1//the-refresh-token") -> tuple[GmailClient, Ended]:
    from hiretitan.mail.infra.google_oauth import GoogleOAuth

    ended = Ended()
    client = GmailClient(
        auth=GoogleOAuth(sleep=no_wait),
        secrets=Secrets(refresh_token),
        on_access_ended=ended,
        sleep=no_wait,
    )
    return client, ended


async def test_US1_AS2_profile_gives_address() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))
        route = router.get(PROFILE_URL).respond(200, json=fixture("profile.json"))

        address = await client.profile()

    assert address == "jobseeker@example.invalid"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer ya29.synthetic-access-token-0003"
    assert request.method == "GET"


async def test_US1_AS2_the_address_is_read_with_the_token_of_a_new_sign_in() -> None:
    with respx.mock() as router:
        route = router.get(PROFILE_URL).respond(200, json=fixture("profile.json"))

        address = await GmailProfile(sleep=no_wait).address_for("ya29.just-granted")

    assert address == "jobseeker@example.invalid"
    assert route.calls.last.request.headers["authorization"] == "Bearer ya29.just-granted"


async def test_FR005_a_401_is_answered_by_one_refresh_and_one_retry() -> None:
    client, ended = make_client()
    with respx.mock() as router:
        token = router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))
        profile = router.get(PROFILE_URL).mock(
            side_effect=[
                httpx.Response(401, json=fixture("unauthorized.json")),
                httpx.Response(200, json=fixture("profile.json")),
            ]
        )

        assert await client.profile() == "jobseeker@example.invalid"

    assert token.call_count == 2  # once to start, once after the 401
    assert profile.call_count == 2
    assert ended.messages == []


async def test_FR005_401_after_refresh_ends_access() -> None:
    client, ended = make_client()
    with respx.mock() as router:
        router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))
        profile = router.get(PROFILE_URL).respond(401, json=fixture("unauthorized.json"))

        with pytest.raises(MailAccessEndedError):
            await client.profile()

    assert profile.call_count == 2  # one retry, never a loop
    assert len(ended.messages) == 1


async def test_FR005_a_revoked_refresh_token_ends_access() -> None:
    client, ended = make_client()
    with respx.mock(assert_all_called=False) as router:
        router.post(TOKEN_URL).respond(400, json=fixture("token_invalid_grant.json"))
        profile = router.get(PROFILE_URL).respond(200, json=fixture("profile.json"))

        with pytest.raises(MailAccessEndedError):
            await client.profile()

    assert profile.call_count == 0  # no mailbox request without a working token
    assert len(ended.messages) == 1


async def test_FR005_no_saved_token_ends_access_without_calling_google() -> None:
    client, ended = make_client(refresh_token=None)
    with respx.mock(assert_all_called=False) as router:
        anything = router.route().respond(500)

        with pytest.raises(MailAccessEndedError):
            await client.profile()

    assert anything.call_count == 0
    assert len(ended.messages) == 1


async def test_FR005_gmail_being_down_is_unavailable_after_retries() -> None:
    client, ended = make_client()
    with respx.mock() as router:
        router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))
        profile = router.get(PROFILE_URL).respond(503)

        with pytest.raises(MailUnavailableError):
            await client.profile()

    assert profile.call_count == 3
    assert ended.messages == []  # an outage is not the end of the person's access


async def test_FR005_a_429_is_retried() -> None:
    client, _ = make_client()
    with respx.mock() as router:
        router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))
        router.get(PROFILE_URL).mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json=fixture("profile.json"))]
        )

        assert await client.profile() == "jobseeker@example.invalid"


async def test_SC007_only_get_on_allowed_paths() -> None:
    client, _ = make_client()
    seen: list[tuple[str, str]] = []

    def record(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json=fixture("token_refresh.json"))
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json=fixture("profile.json"))

    with respx.mock() as router:
        router.route().mock(side_effect=record)  # every request, whatever its verb or path
        await client.profile()
        await GmailProfile(sleep=no_wait).address_for("ya29.x")

    assert seen
    for method, path in seen:
        assert method == "GET", f"{method} {path} is not a read"
        assert ALLOWED_PATH.match(path), f"{path} is not one of the three paths"
