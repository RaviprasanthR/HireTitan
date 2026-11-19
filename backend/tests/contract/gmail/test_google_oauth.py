"""Google sign-in contract (T012): FR-002, FR-004, FR-005, SC-007.

The answers are the provisional fixtures in ``tests/fixtures/gmail`` (see its README) until the
recordings of T004 replace them. A catch-all route logs every request, so a call to anything but
``/token`` and ``/revoke`` on Google's sign-in host fails the test.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from hiretitan.mail.application.ports import MailAccessEndedError, MailUnavailableError
from hiretitan.mail.domain.oauth import READONLY_SCOPE, code_challenge
from hiretitan.mail.infra.google_oauth import GoogleOAuth

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "gmail"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CLIENT = {"client_id": "client-id-1234567890", "client_secret": "client-secret-1234567890"}
REDIRECT = "http://localhost:8000/api/v1/mail/google/callback"


def fixture(name: str) -> dict[str, object]:
    data = json.loads((FIXTURES / name).read_text("utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture
def google() -> GoogleOAuth:
    async def no_wait(_seconds: float) -> None:
        return None

    return GoogleOAuth(sleep=no_wait)


def form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_FR002_authorize_url_asks_only_readonly(google: GoogleOAuth) -> None:
    verifier = "v" * 64
    url = google.authorize_url(
        client_id=CLIENT["client_id"],
        redirect_uri=REDIRECT,
        state="the-state",
        code_challenge=code_challenge(verifier),
    )

    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert query["scope"] == READONLY_SCOPE  # one scope, nothing wider
    assert query["access_type"] == "offline"  # a refresh token, so the daily check can run
    assert query["prompt"] == "consent"
    assert query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256"
    assert query["code_challenge"] == code_challenge(verifier)
    assert query["state"] == "the-state"
    assert query["redirect_uri"] == REDIRECT
    assert query["client_id"] == CLIENT["client_id"]
    assert "client_secret" not in query


async def test_US1_AS2_code_exchange(google: GoogleOAuth) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post(TOKEN_URL).respond(200, json=fixture("token_exchange.json"))

        grant = await google.exchange_code(
            **CLIENT, redirect_uri=REDIRECT, code="the-code", code_verifier="the-verifier"
        )

    sent = form(route.calls.last.request)
    assert sent == {
        "grant_type": "authorization_code",
        "code": "the-code",
        "code_verifier": "the-verifier",
        "redirect_uri": REDIRECT,
        **CLIENT,
    }
    assert grant.scope == READONLY_SCOPE
    assert grant.refresh_token == "1//0g-synthetic-refresh-token-0002"
    assert grant.access_token == "ya29.synthetic-access-token-0001"
    assert "ya29" not in repr(grant)  # the tokens stay out of a stray log line


async def test_US1_AS2_a_refused_code_is_access_ended(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        router.post(TOKEN_URL).respond(400, json=fixture("token_invalid_grant.json"))

        with pytest.raises(MailAccessEndedError):
            await google.exchange_code(
                **CLIENT, redirect_uri=REDIRECT, code="used-twice", code_verifier="v"
            )


async def test_FR005_refresh_gives_a_new_access_token(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        route = router.post(TOKEN_URL).respond(200, json=fixture("token_refresh.json"))

        token = await google.refresh(**CLIENT, refresh_token="1//the-refresh-token")

    assert token == "ya29.synthetic-access-token-0003"
    assert form(route.calls.last.request) == {
        "grant_type": "refresh_token",
        "refresh_token": "1//the-refresh-token",
        **CLIENT,
    }


async def test_FR005_refresh_invalid_grant_needs_reconnect(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        route = router.post(TOKEN_URL).respond(400, json=fixture("token_invalid_grant.json"))

        with pytest.raises(MailAccessEndedError):
            await google.refresh(**CLIENT, refresh_token="1//revoked")

    assert route.call_count == 1  # a refusal is final: no retries


async def test_FR005_google_being_down_is_unavailable_not_access_ended(
    google: GoogleOAuth,
) -> None:
    with respx.mock() as router:
        route = router.post(TOKEN_URL).respond(503, json={"error": "backend_error"})

        with pytest.raises(MailUnavailableError):
            await google.refresh(**CLIENT, refresh_token="1//x")

    assert route.call_count == 3  # tried, then gave up


async def test_FR005_a_network_error_is_unavailable(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        router.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("no route"))

        with pytest.raises(MailUnavailableError):
            await google.refresh(**CLIENT, refresh_token="1//x")


async def test_FR004_revoke(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        route = router.post(REVOKE_URL).respond(200, json=fixture("revoke_ok.json"))

        await google.revoke("1//the-refresh-token")

    assert form(route.calls.last.request) == {"token": "1//the-refresh-token"}


async def test_FR004_revoking_an_already_revoked_token_is_fine(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        router.post(REVOKE_URL).respond(400, json={"error": "invalid_token"})

        await google.revoke("1//already-gone")  # nothing left to revoke; not an error


async def test_FR004_revoke_when_google_is_down_is_unavailable(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        router.post(REVOKE_URL).respond(500)

        with pytest.raises(MailUnavailableError):
            await google.revoke("1//x")


async def test_SC007_oauth_only_posts_token_and_revoke(google: GoogleOAuth) -> None:
    seen: list[tuple[str, str]] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.host + request.url.path))
        if request.url.path == "/token":
            return httpx.Response(200, json=fixture("token_exchange.json"))
        return httpx.Response(200, json={})

    with respx.mock() as router:
        router.route().mock(side_effect=record)  # every request, whatever it is
        await google.exchange_code(**CLIENT, redirect_uri=REDIRECT, code="c", code_verifier="v")
        await google.refresh(**CLIENT, refresh_token="1//r")
        await google.revoke("1//r")

    assert set(seen) == {
        ("POST", "oauth2.googleapis.com/token"),
        ("POST", "oauth2.googleapis.com/revoke"),
    }
    assert all("gmail" not in host for _method, host in seen)  # never the mailbox from here


async def test_FR003_secrets_are_not_in_the_error_text(google: GoogleOAuth) -> None:
    with respx.mock() as router:
        router.post(TOKEN_URL).respond(400, json=fixture("token_invalid_grant.json"))

        with pytest.raises(MailAccessEndedError) as caught:
            await google.refresh(**CLIENT, refresh_token="1//super-secret-refresh")

    text = str(caught.value) + repr(caught.value)
    assert CLIENT["client_secret"] not in text
    assert "super-secret-refresh" not in text
