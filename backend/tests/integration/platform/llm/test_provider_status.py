"""T024: provider status (FR-029): is the AI key missing, working, rejected or unreachable?"""

from __future__ import annotations

from typing import Any

import httpx2
import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.openai_adapter import OpenAiAdapter
from hiretitan.platform.llm.port import AiUnavailable, LlmRequest, RenderedPrompt
from hiretitan.platform.llm.provider_status import ProviderStatusService

SECRET = "sk-test-very-secret-key"


class Answer(BaseModel):
    answer: str


class Network:
    """A mock transport that records calls and answers with a fixed status."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        body = {"object": "list", "data": []} if self.status == 200 else {"error": {"message": "x"}}
        return httpx2.Response(self.status, json=body)

    def client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self))


class Events:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, event: str, data: dict[str, Any]) -> None:
        self.published.append((event, data))


def service(
    sessions: async_sessionmaker[AsyncSession], network: Network, *, key: str | None, events: Events
) -> tuple[ProviderStatusService, OpenAiAdapter]:
    holder: list[ProviderStatusService] = []

    async def rejected() -> None:
        await holder[0].mark_rejected()

    adapter = OpenAiAdapter(
        SecretStr(key) if key else None,
        ModelCatalog.load(),
        http_client=network.client(),
        on_key_rejected=rejected,
    )
    status = ProviderStatusService(sessions, adapter, has_key=key is not None, publish=events)
    holder.append(status)
    return status, adapter


async def stored(sessions: async_sessionmaker[AsyncSession]) -> tuple[str, str | None]:
    async with sessions() as session:
        row = await ProviderStatusRepo(session).get("openai")
    assert row is not None
    return row.status, row.message


async def test_unknown_until_checked(sessions: async_sessionmaker[AsyncSession]) -> None:
    assert (await stored(sessions))[0] == "unknown"


async def test_FR029_missing_key_detected_without_network(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    network, events = Network(), Events()
    status, _ = service(sessions, network, key=None, events=events)
    assert await status.check() == "missing"
    assert network.requests == []
    assert (await stored(sessions))[0] == "missing"
    assert events.published == [("status.updated", {"ai_status": "missing"})]


async def test_working_key(sessions: async_sessionmaker[AsyncSession]) -> None:
    network, events = Network(200), Events()
    status, _ = service(sessions, network, key=SECRET, events=events)
    assert await status.check() == "working"
    assert network.requests[0].url.path == "/v1/models"
    assert (await stored(sessions))[0] == "working"


async def test_FR029_rejected_status_written_on_401(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    events = Events()
    status, adapter = service(sessions, Network(401), key=SECRET, events=events)

    # 1. the explicit key check
    assert await status.check() == "rejected"
    assert (await stored(sessions))[0] == "rejected"

    # 2. a real call that gets a 401 also marks the key rejected
    async with sessions() as session:
        await ProviderStatusRepo(session).set("openai", "working", None)
        await session.commit()
    request = LlmRequest(
        task="t",
        prompt=RenderedPrompt("t", 1, "s", "u"),
        output_schema=Answer,
        tier="fast",
        max_output_tokens=10,
    )
    with pytest.raises(AiUnavailable) as raised:
        await adapter.generate(request)
    assert raised.value.reason == "key_rejected"
    assert (await stored(sessions))[0] == "rejected"
    assert ("status.updated", {"ai_status": "rejected"}) in events.published


async def test_unreachable(sessions: async_sessionmaker[AsyncSession]) -> None:
    status, _ = service(sessions, Network(503), key=SECRET, events=Events())
    assert await status.check() == "unreachable"


async def test_status_never_contains_key(sessions: async_sessionmaker[AsyncSession]) -> None:
    events = Events()
    for http_status in (200, 401, 503):
        status, _ = service(sessions, Network(http_status), key=SECRET, events=events)
        await status.check()
        _, message = await stored(sessions)
        assert SECRET not in (message or "")
    status, _ = service(sessions, Network(), key=None, events=events)
    await status.check()
    async with sessions() as session:
        dump = (
            await session.execute(text("SELECT row_to_json(p)::text FROM app.provider_status p"))
        ).scalar_one()
    assert SECRET not in dump
    assert SECRET not in repr(events.published)


def test_check_provider_key_is_a_registered_queue_task() -> None:
    from hiretitan.platform.runtime.procrastinate import CHECK_PROVIDER_KEY_TASK, create_runtime

    runtime = create_runtime("postgresql+psycopg://u:p@localhost/db")
    assert CHECK_PROVIDER_KEY_TASK in runtime.app.tasks
