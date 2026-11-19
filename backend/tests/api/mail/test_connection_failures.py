"""Connection edge cases found in the T019r review: damaged files, partial failures, races, a
changed client. Same fake Google and real database as ``test_connection_api``."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.api.mail.test_connection_api import (
    CLIENT_ID,
    CLIENT_SECRET,
    REFRESH,
    Env,
    build,
    connect,
    save_credentials,
)

from hiretitan.mail.application.ports import SecretsFileError


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    made = build(sessions, tmp_path, {})
    yield made
    await made.client.aclose()


async def test_US1_AS4_the_service_marks_needs_reconnect_and_says_so(env: Env) -> None:
    await save_credentials(env)
    await connect(env)
    env.events.clear()

    await env.service.mark_needs_reconnect("Gmail access has ended. Connect again.")

    body = (await env.client.get("/api/v1/mail/connection")).json()
    assert (body["state"], body["last_error"]) == (
        "needs_reconnect",
        "Gmail access has ended. Connect again.",
    )
    assert env.events == [("mail.connection_changed", {"state": "needs_reconnect"})]


async def test_FR004_disconnect_stops_the_check_then_revokes(env: Env) -> None:
    await save_credentials(env)
    await connect(env)
    env.google.calls.clear()

    await env.client.delete("/api/v1/mail/connection")

    assert env.google.calls == ["stop", "revoke"]  # nothing is revoked while a check still runs


async def test_FR003_a_damaged_secrets_file_gives_clear_answers_not_500s(
    env: Env, tmp_path: Path
) -> None:
    path = tmp_path / "data" / "secrets" / "gmail.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", "utf-8")

    put = await env.client.put(
        "/api/v1/mail/credentials", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    )
    started = await env.client.post("/api/v1/mail/connect")
    callback = await env.client.get(
        "/api/v1/mail/google/callback", params={"code": "c", "state": "s"}
    )

    assert (put.status_code, put.json()["reason"]) == (503, "secrets_unreadable")
    assert (started.status_code, started.json()["reason"]) == (503, "secrets_unreadable")
    assert callback.status_code == 302


async def test_US1_AS3_disconnect_works_even_with_a_damaged_secrets_file(
    env: Env, tmp_path: Path
) -> None:
    await save_credentials(env)
    await connect(env)
    path = tmp_path / "data" / "secrets" / "gmail.json"
    path.write_text("{not json", "utf-8")

    response = await env.client.delete("/api/v1/mail/connection")

    assert response.status_code == 200
    assert not path.exists()  # the damaged file goes, so the person can start again
    assert (await env.client.get("/api/v1/mail/connection")).json()["state"] == "not_connected"


async def test_US1_an_event_that_cannot_be_published_does_not_fail_the_request(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    made = build(sessions, tmp_path, {})

    async def broken(name: str, data: dict[str, Any]) -> None:
        raise RuntimeError("the notify channel is down")

    made.service._publish = broken
    try:
        await save_credentials(made)
        assert (await connect(made)).headers["location"] == "/settings?gmail=connected"
        assert (await made.client.delete("/api/v1/mail/connection")).status_code == 200
    finally:
        await made.client.aclose()


async def test_FR002_a_failure_saving_the_token_revokes_it_and_reports_exchange_failed(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await save_credentials(env)

    def broken(_token: str) -> None:
        raise SecretsFileError("busy")

    monkeypatch.setattr(env.secrets, "save_refresh_token", broken)

    response = await connect(env)

    assert response.headers["location"] == "/settings?gmail=error&reason=exchange_failed"
    assert env.google.revoked == [REFRESH]  # no live token is left at Google that is not kept here
    assert (await env.client.get("/api/v1/mail/connection")).json()["state"] == "not_connected"


async def test_US1_a_disconnect_during_a_sign_in_is_not_undone_by_it(env: Env) -> None:
    await save_credentials(env)
    await connect(env)
    gate = asyncio.Event()
    env.google.hold_profile = gate
    env.google.profile_started.clear()
    started = await env.client.post("/api/v1/mail/connect")
    state = parse_qs(urlsplit(started.json()["authorize_url"]).query)["state"][0]

    callback = asyncio.create_task(
        env.client.get("/api/v1/mail/google/callback", params={"code": "c", "state": state})
    )
    await env.google.profile_started.wait()  # the sign-in is waiting on Google
    disconnect = asyncio.create_task(env.client.delete("/api/v1/mail/connection"))
    await asyncio.sleep(0.05)
    gate.set()
    await asyncio.gather(callback, disconnect)

    # the person pressed Disconnect last, so the end state is disconnected, token gone
    assert (await env.client.get("/api/v1/mail/connection")).json()["state"] == "not_connected"
    assert env.secrets.read().refresh_token is None


async def test_FR002_changing_the_client_while_connected_revokes_and_asks_to_reconnect(
    env: Env,
) -> None:
    await save_credentials(env)
    await connect(env)

    response = await env.client.put(
        "/api/v1/mail/credentials",
        json={"client_id": "another-client-id-1234", "client_secret": "another-secret-5678"},
    )

    assert response.json()["state"] == "needs_reconnect"
    assert env.google.revoked == [REFRESH]  # the old client's token is handed back
    assert env.secrets.read().refresh_token is None


async def test_FR002_the_same_client_keeps_the_connection(env: Env) -> None:
    await save_credentials(env)
    await connect(env)

    response = await env.client.put(
        "/api/v1/mail/credentials",
        json={"client_id": CLIENT_ID, "client_secret": "a-rotated-secret-12345"},
    )

    assert response.json()["state"] == "connected"
    assert env.google.revoked == []


async def test_FR004_reconnecting_revokes_the_previous_token(env: Env) -> None:
    await save_credentials(env)
    await connect(env)
    env.google.refresh_token = "1//0g-a-second-refresh-token-0003"

    await connect(env)

    assert env.google.revoked == [REFRESH]
    assert env.secrets.read().refresh_token == "1//0g-a-second-refresh-token-0003"


async def test_US1_callback_an_oversized_value_is_a_state_error_not_a_422(env: Env) -> None:
    response = await env.client.get(
        "/api/v1/mail/google/callback", params={"code": "c" * 5000, "state": "s" * 5000}
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/settings?gmail=error&reason=state"
