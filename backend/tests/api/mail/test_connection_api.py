"""Connect, show and disconnect Gmail (T014): US1, FR-001 to FR-005. Fake Google, real database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.google import ACCESS, REFRESH, FakeGoogle
from tests.fakes.mail_env import make_job, make_run

from hiretitan.api_main import create_app
from hiretitan.mail.api.connection import MailApiDeps, create_connection_router
from hiretitan.mail.application.connection import ConnectionService
from hiretitan.mail.application.consents import PendingConsents
from hiretitan.mail.infra.models import MailCheckRow, MailReadMessageRow
from hiretitan.mail.infra.repos import ConnectionRepo, MailChecksRepo, ReadMessagesRepo
from hiretitan.mail.infra.secrets_file import SecretsFile
from hiretitan.mail.infra.store import SqlMailStore
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.infra.models import JobRow

CLIENT_ID = "1234567890-abcdefghij.apps.googleusercontent.invalid"
CLIENT_SECRET = "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"
REDIRECT = "http://localhost:8000/api/v1/mail/google/callback"
NOW = datetime(2026, 11, 18, 9, tzinfo=UTC)


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    google: FakeGoogle
    secrets: SecretsFile
    clock: FakeClock
    service: ConnectionService
    stops: list[int] = field(default_factory=list)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


def build(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path, environ: dict[str, str]
) -> Env:
    google = FakeGoogle()
    secrets = SecretsFile(tmp_path / "data" / "secrets" / "gmail.json", environ)
    clock = FakeClock(NOW)
    stops: list[int] = []
    events: list[tuple[str, dict[str, Any]]] = []

    async def stop_check() -> None:
        stops.append(1)
        google.calls.append("stop")

    async def publish(name: str, data: dict[str, Any]) -> None:
        events.append((name, data))

    service = ConnectionService(
        store=SqlMailStore(sessions),
        secrets=secrets,
        auth=google,
        profile=google,
        consents=PendingConsents(clock),
        clock=clock,
        redirect_uri=REDIRECT,
        stop_check=stop_check,
        publish=publish,
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[create_connection_router(MailApiDeps(service))],
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return Env(client, sessions, google, secrets, clock, service, stops, events)


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    made = build(sessions, tmp_path, {})
    yield made
    await made.client.aclose()


async def save_credentials(env: Env) -> None:
    response = await env.client.put(
        "/api/v1/mail/credentials", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    )
    assert response.status_code == 200, response.text


async def connect(env: Env, *, code: str = "the-code") -> httpx.Response:
    """The whole sign-in: start it, then Google sends the browser back with the state."""
    started = await env.client.post("/api/v1/mail/connect")
    assert started.status_code == 200, started.text
    state = parse_qs(urlsplit(started.json()["authorize_url"]).query)["state"][0]
    return await env.client.get(
        "/api/v1/mail/google/callback", params={"code": code, "state": state}
    )


async def test_US1_AS1_not_connected_state(env: Env) -> None:
    body = (await env.client.get("/api/v1/mail/connection")).json()

    assert body == {
        "state": "not_connected",
        "address": None,
        "credentials_set": False,
        "credentials_from_environment": False,
        "redirect_uri": REDIRECT,
        "last_check_started_at": None,
        "last_error": None,
        "window_hours": 24,
    }


async def test_US1_AS5_connect_without_credentials_409(env: Env) -> None:
    response = await env.client.post("/api/v1/mail/connect")

    assert response.status_code == 409
    assert response.json()["reason"] == "no_credentials"
    assert env.google.calls == []  # nothing was sent to Google


async def test_FR001_no_shipped_credentials_connect_needs_the_persons_own(
    env: Env, tmp_path: Path
) -> None:
    # a fresh install has no client id or secret anywhere, so the person must bring their own
    assert not (tmp_path / "data" / "secrets" / "gmail.json").exists()
    assert (await env.client.get("/api/v1/mail/connection")).json()["credentials_set"] is False
    assert (await env.client.post("/api/v1/mail/connect")).status_code == 409


@pytest.mark.parametrize(
    "bad",
    [
        {"client_id": "short", "client_secret": CLIENT_SECRET},
        {"client_id": CLIENT_ID, "client_secret": "has a space in it"},
        {"client_id": "x" * 301, "client_secret": CLIENT_SECRET},
        {"client_id": CLIENT_ID},
    ],
)
async def test_US1_AS5_credentials_must_be_plain_and_a_sensible_length(
    env: Env, bad: dict[str, str]
) -> None:
    assert (await env.client.put("/api/v1/mail/credentials", json=bad)).status_code == 422


async def test_US1_AS5_saving_the_credentials_shows_them_set_but_never_their_values(
    env: Env,
) -> None:
    response = await env.client.put(
        "/api/v1/mail/credentials", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    )

    assert response.status_code == 200
    assert response.json()["credentials_set"] is True
    assert CLIENT_SECRET not in response.text


async def test_US1_AS2_connect_asks_google_for_read_only_and_a_one_time_state(env: Env) -> None:
    await save_credentials(env)

    response = await env.client.post("/api/v1/mail/connect")

    url = response.json()["authorize_url"]
    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["state"][0]
    assert query["code_challenge"][0]


async def test_US1_AS2_callback_connects_and_redirects(env: Env) -> None:
    await save_credentials(env)

    response = await connect(env)

    assert response.status_code == 302
    assert response.headers["location"] == "/settings?gmail=connected"
    assert env.secrets.read().refresh_token == REFRESH
    assert env.google.exchanged[0]["code"] == "the-code"
    assert env.google.exchanged[0]["code_verifier"]  # PKCE: the verifier goes with the code
    body = (await env.client.get("/api/v1/mail/connection")).json()
    assert (body["state"], body["address"]) == ("connected", "jobseeker@example.invalid")
    assert ("mail.connection_changed", {"state": "connected"}) in env.events


@pytest.mark.parametrize("params", [{"code": "c", "state": "not-a-state"}, {"code": "c"}])
async def test_US1_callback_bad_state_redirects_with_error(
    env: Env, params: dict[str, str]
) -> None:
    await save_credentials(env)

    response = await env.client.get("/api/v1/mail/google/callback", params=params)

    assert response.status_code == 302
    assert response.headers["location"] == "/settings?gmail=error&reason=state"
    assert "exchange_code" not in env.google.calls
    assert (await env.client.get("/api/v1/mail/connection")).json()["state"] == "not_connected"


async def test_US1_callback_state_works_once_only(env: Env) -> None:
    await save_credentials(env)
    started = await env.client.post("/api/v1/mail/connect")
    state = parse_qs(urlsplit(started.json()["authorize_url"]).query)["state"][0]
    params = {"code": "c", "state": state}

    first = await env.client.get("/api/v1/mail/google/callback", params=params)
    second = await env.client.get("/api/v1/mail/google/callback", params=params)

    assert first.headers["location"] == "/settings?gmail=connected"
    assert second.headers["location"] == "/settings?gmail=error&reason=state"


async def test_US1_callback_state_expires_after_ten_minutes(env: Env) -> None:
    from datetime import timedelta

    await save_credentials(env)
    started = await env.client.post("/api/v1/mail/connect")
    state = parse_qs(urlsplit(started.json()["authorize_url"]).query)["state"][0]
    env.clock.advance(timedelta(minutes=10, seconds=1))

    response = await env.client.get(
        "/api/v1/mail/google/callback", params={"code": "c", "state": state}
    )

    assert response.headers["location"] == "/settings?gmail=error&reason=state"


async def test_US1_callback_the_person_said_no(env: Env) -> None:
    await save_credentials(env)
    started = await env.client.post("/api/v1/mail/connect")
    state = parse_qs(urlsplit(started.json()["authorize_url"]).query)["state"][0]

    response = await env.client.get(
        "/api/v1/mail/google/callback", params={"error": "access_denied", "state": state}
    )

    assert response.headers["location"] == "/settings?gmail=error&reason=denied"
    assert env.google.calls.count("exchange_code") == 0


async def test_US1_callback_exchange_failure_is_reported(env: Env) -> None:
    await save_credentials(env)
    env.google.exchange_fails = True

    response = await connect(env)

    assert response.headers["location"] == "/settings?gmail=error&reason=exchange_failed"
    assert env.secrets.read().refresh_token is None
    assert (await env.client.get("/api/v1/mail/connection")).json()["state"] == "not_connected"


async def test_FR002_callback_wrong_scope_revokes(env: Env) -> None:
    await save_credentials(env)
    env.google.scope = (
        "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
    )

    response = await connect(env)

    assert response.headers["location"] == "/settings?gmail=error&reason=wrong_scope"
    assert env.google.revoked == [REFRESH]  # the wider grant is handed back at once
    assert env.secrets.read().refresh_token is None
    assert "profile" not in env.google.calls  # the mailbox was never touched
    assert (await env.client.get("/api/v1/mail/connection")).json()["state"] == "not_connected"


async def test_FR002_a_different_read_scope_is_also_refused(env: Env) -> None:
    await save_credentials(env)
    env.google.scope = "https://www.googleapis.com/auth/gmail.metadata"

    response = await connect(env)

    assert response.headers["location"].endswith("reason=wrong_scope")
    assert env.google.revoked == [REFRESH]


async def test_FR002_a_grant_without_a_refresh_token_revokes_the_access_token(env: Env) -> None:
    await save_credentials(env)
    env.google.refresh_token = None

    response = await connect(env)

    assert response.headers["location"].endswith("reason=exchange_failed")
    assert env.google.revoked == [ACCESS]


async def test_US1_AS3_disconnect_revokes_and_deletes_keeps_jobs(env: Env) -> None:
    await save_credentials(env)
    await connect(env)
    async with env.sessions() as session:
        job_id = await make_job(session)
        await session.commit()

    response = await env.client.delete("/api/v1/mail/connection")

    assert response.status_code == 200
    assert response.json() == {"revoked": True}
    assert env.google.revoked == [REFRESH]
    read = env.secrets.read()
    assert read.refresh_token is None
    assert read.client_id == CLIENT_ID  # the person's own client stays, so reconnecting is quick
    body = (await env.client.get("/api/v1/mail/connection")).json()
    assert (body["state"], body["address"]) == ("not_connected", None)
    async with env.sessions() as session:
        assert await session.get(JobRow, job_id) is not None
    assert ("mail.connection_changed", {"state": "not_connected"}) in env.events


async def test_FR004_disconnect_stops_a_running_check_and_deletes_read_email_and_check_records(
    env: Env,
) -> None:
    await save_credentials(env)
    await connect(env)
    async with env.sessions() as session:
        run_id = await make_run(session)
        check = await MailChecksRepo(session).create(run_id, "button", NOW)
        await ReadMessagesRepo(session).record(
            "m1", "a@x.example.invalid", NOW, "read", "naukri", 1, [], check.id, NOW
        )
        await session.commit()

    assert (await env.client.delete("/api/v1/mail/connection")).status_code == 200

    assert env.stops == [1]  # a running check was asked to stop before anything was removed
    async with env.sessions() as session:
        assert await session.scalar(select(func.count(MailReadMessageRow.id))) == 0
        assert await session.scalar(select(func.count(MailCheckRow.id))) == 0
        assert await ConnectionRepo(session).get() is None


async def test_US1_AS3_disconnect_removes_everything_even_when_google_cannot_be_reached(
    env: Env,
) -> None:
    await save_credentials(env)
    await connect(env)
    env.google.revoke_fails = True

    response = await env.client.delete("/api/v1/mail/connection")

    # best effort with Google; the local data goes anyway, and the person is told
    assert response.status_code == 200
    assert response.json() == {"revoked": False}
    assert env.secrets.read().refresh_token is None
    assert (await env.client.get("/api/v1/mail/connection")).json()["state"] == "not_connected"


async def test_US1_disconnect_when_not_connected_is_fine(env: Env) -> None:
    response = await env.client.delete("/api/v1/mail/connection")

    assert response.status_code == 200
    assert response.json() == {"revoked": True}  # nothing to hand back counts as done


async def test_US1_AS4_needs_reconnect_shown(env: Env) -> None:
    await save_credentials(env)
    await connect(env)

    async with env.sessions() as session:
        await ConnectionRepo(session).set_state("needs_reconnect", "Gmail access has ended.")
        await session.commit()

    body = (await env.client.get("/api/v1/mail/connection")).json()
    assert (body["state"], body["last_error"]) == ("needs_reconnect", "Gmail access has ended.")
    assert body["address"] == "jobseeker@example.invalid"


async def test_US1_AS4_reconnecting_clears_the_notice(env: Env) -> None:
    await save_credentials(env)
    await connect(env)
    async with env.sessions() as session:
        await ConnectionRepo(session).set_state("needs_reconnect", "Gmail access has ended.")
        await session.commit()

    response = await connect(env)

    assert response.headers["location"] == "/settings?gmail=connected"
    body = (await env.client.get("/api/v1/mail/connection")).json()
    assert (body["state"], body["last_error"]) == ("connected", None)


async def test_FR003_no_secret_in_any_response(env: Env) -> None:
    await save_credentials(env)
    texts = [
        (await env.client.get("/api/v1/mail/connection")).text,
        (await env.client.post("/api/v1/mail/connect")).text,
        (await connect(env)).text,
        str((await connect(env)).headers),
        (await env.client.get("/api/v1/mail/connection")).text,
        (await env.client.delete("/api/v1/mail/connection")).text,
    ]

    everything = "\n".join(texts)
    for secret in (CLIENT_SECRET, REFRESH, ACCESS):
        assert secret not in everything


async def test_credentials_from_environment_409(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    made = build(
        sessions,
        tmp_path,
        {"GOOGLE_OAUTH_CLIENT_ID": CLIENT_ID, "GOOGLE_OAUTH_CLIENT_SECRET": CLIENT_SECRET},
    )
    try:
        shown = (await made.client.get("/api/v1/mail/connection")).json()
        assert shown["credentials_set"] is True
        assert shown["credentials_from_environment"] is True

        response = await made.client.put(
            "/api/v1/mail/credentials",
            json={"client_id": "another-client-id-1234", "client_secret": "another-secret-5678"},
        )

        assert response.status_code == 409
        assert response.json()["reason"] == "credentials_from_environment"
        assert (await connect(made)).headers["location"] == "/settings?gmail=connected"
    finally:
        await made.client.aclose()


async def test_FR003_a_damaged_secrets_file_does_not_break_the_page(
    env: Env, tmp_path: Path
) -> None:
    path = tmp_path / "data" / "secrets" / "gmail.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", "utf-8")

    response = await env.client.get("/api/v1/mail/connection")

    assert response.status_code == 200
    body = response.json()
    assert body["credentials_set"] is False
    assert "secrets file" in (body["last_error"] or "")
