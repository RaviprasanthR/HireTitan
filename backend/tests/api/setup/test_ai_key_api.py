"""T053: the AI key from Settings over the API (US6 AS2-AS4, FR-029, FR-030, SC-010)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.key_store import KeyStore
from hiretitan.setup.api.ai_key import AiKeyApiDeps, create_ai_key_router
from hiretitan.setup.api.status import StatusApiDeps, create_status_router
from hiretitan.setup_wiring import RepoFacts

KEY = "sk-test-0123456789abcdefghij"


@dataclass
class Env:
    client: httpx.AsyncClient
    keys: KeyStore
    checks: list[int] = field(default_factory=list)


async def make_env(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path, env_key: str | None = None
) -> AsyncIterator[Env]:
    keys = KeyStore(tmp_path / "secrets" / "llm.json", SecretStr(env_key) if env_key else None)
    checks: list[int] = []

    async def enqueue_key_check() -> None:
        checks.append(1)

    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_ai_key_router(AiKeyApiDeps(keys=keys, enqueue_key_check=enqueue_key_check)),
            create_status_router(
                StatusApiDeps(
                    sessions=sessions,
                    clock=FakeClock(),
                    provider="openai",
                    facts=RepoFacts,
                    enqueue_key_check=enqueue_key_check,
                    key_source=lambda: keys.current()[1],
                )
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, keys, checks)


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    async for value in make_env(sessions, tmp_path):
        yield value


@pytest.fixture
async def env_from_dotenv(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[Env]:
    async for value in make_env(sessions, tmp_path, env_key=KEY):
        yield value


async def test_US6_AS2_save_checks_the_key_202(env: Env) -> None:
    response = await env.client.put("/api/v1/settings/ai-key", json={"key": f"  {KEY} "})

    assert response.status_code == 202
    assert response.json() == {"key_source": "page", "status": "unknown"}
    assert env.keys.current() == (KEY, "page")
    assert env.checks == [1]  # the worker checks it, then resumes what the key had paused


async def test_US6_AS3_key_never_returned(env: Env) -> None:
    saved = await env.client.put("/api/v1/settings/ai-key", json={"key": KEY})
    status = await env.client.get("/api/v1/status")

    assert KEY not in saved.text
    assert KEY not in status.text
    assert status.json()["ai"]["key_source"] == "page"


async def test_US6_AS4_env_key_409(env_from_dotenv: Env) -> None:
    env = env_from_dotenv
    put = await env.client.put("/api/v1/settings/ai-key", json={"key": "sk-other-0123456789abcdef"})
    delete = await env.client.delete("/api/v1/settings/ai-key")
    status = await env.client.get("/api/v1/status")

    assert (put.status_code, put.json()["reason"]) == (409, "key_from_environment")
    assert (delete.status_code, delete.json()["reason"]) == (409, "key_from_environment")
    assert status.json()["ai"]["key_source"] == "env"
    assert KEY not in put.text + delete.text + status.text
    assert env.checks == []


@pytest.mark.parametrize("bad", ["short", "has a space-0123456789abc", "x" * 301, ""])
async def test_FR029_bad_shape_422(env: Env, bad: str) -> None:
    response = await env.client.put("/api/v1/settings/ai-key", json={"key": bad})

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert [e["field"] for e in errors] == ["key"]
    assert bad not in response.text or bad == ""  # the rejected value is not echoed
    assert env.keys.current() == (None, "none")


async def test_a_body_with_more_than_the_key_422(env: Env) -> None:
    response = await env.client.put(
        "/api/v1/settings/ai-key", json={"key": KEY, "provider": "other"}
    )

    assert response.status_code == 422


async def test_remove_204(env: Env) -> None:
    await env.client.put("/api/v1/settings/ai-key", json={"key": KEY})

    response = await env.client.delete("/api/v1/settings/ai-key")

    assert response.status_code == 204
    assert env.keys.current() == (None, "none")
    assert (await env.client.get("/api/v1/status")).json()["ai"]["key_source"] == "none"
    assert env.checks == [1, 1]  # the check after removing marks the key missing


async def test_SC010_key_in_no_response_or_log(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        responses = [
            await env.client.put("/api/v1/settings/ai-key", json={"key": KEY}),
            await env.client.get("/api/v1/status"),
            await env.client.put("/api/v1/settings/ai-key", json={"key": KEY + "x"}),
            await env.client.delete("/api/v1/settings/ai-key"),
        ]

    assert all(KEY not in r.text for r in responses)
    assert KEY not in caplog.text
