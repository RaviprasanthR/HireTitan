"""T052: the adapter asks for the current key on every request (FR-030: no restart)."""

from __future__ import annotations

from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr
from tests.contract.openai.test_openai_adapter import Server, fixture, request

from hiretitan.platform.llm.key_store import KeyStore
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.openai_adapter import OpenAiAdapter
from hiretitan.platform.llm.port import AiUnavailable

FIRST = "sk-test-first-0123456789abc"
SECOND = "sk-test-second-0123456789ab"


def adapter_over(server: Server, keys: KeyStore) -> OpenAiAdapter:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(server))
    return OpenAiAdapter(lambda: keys.current()[0], ModelCatalog.load(), http_client=client)


async def test_FR030_the_adapter_uses_the_current_key(tmp_path: Path) -> None:
    keys = KeyStore(tmp_path / "llm.json", None)
    server = Server(*[(200, fixture("response_ok.json"))] * 2)
    adapter = adapter_over(server, keys)

    with pytest.raises(AiUnavailable) as missing:
        await adapter.generate(request())
    assert missing.value.reason == "key_missing"
    assert server.requests == []  # no request without a key

    keys.save(FIRST)
    await adapter.generate(request())
    keys.save(SECOND)
    await adapter.generate(request())

    sent = [r.headers["authorization"] for r in server.requests]
    assert sent == [f"Bearer {FIRST}", f"Bearer {SECOND}"]


async def test_FR030_removing_the_key_stops_ai_calls(tmp_path: Path) -> None:
    keys = KeyStore(tmp_path / "llm.json", None)
    keys.save(FIRST)
    server = Server((200, fixture("response_ok.json")))
    adapter = adapter_over(server, keys)
    await adapter.generate(request())

    keys.remove()

    with pytest.raises(AiUnavailable):
        await adapter.generate(request())
    assert len(server.requests) == 1


async def test_FR030_the_key_check_uses_the_current_key(tmp_path: Path) -> None:
    keys = KeyStore(tmp_path / "llm.json", None)
    keys.save(FIRST)
    server = Server((200, {"object": "list", "data": []}))

    assert await adapter_over(server, keys).check_key() == "working"
    assert server.requests[0].headers["authorization"] == f"Bearer {FIRST}"


async def test_a_fixed_key_still_works_as_before() -> None:
    server = Server((200, fixture("response_ok.json")))
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(server))
    adapter = OpenAiAdapter(SecretStr(FIRST), ModelCatalog.load(), http_client=client)

    await adapter.generate(request())

    assert server.requests[0].headers["authorization"] == f"Bearer {FIRST}"
