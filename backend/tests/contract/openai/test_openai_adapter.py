"""T023: the OpenAI adapter against recorded-shape responses (no network).

The SDK uses ``httpx2``, which ``respx`` cannot intercept, so the adapter takes an
``http_client`` and these tests give it an ``httpx2.MockTransport``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel, SecretStr

from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.openai_adapter import OpenAiAdapter
from hiretitan.platform.llm.port import (
    AiUnavailable,
    LlmRequest,
    RenderedPrompt,
    RetryableLlmError,
    UntrustedText,
)

FIXTURES = Path(__file__).parent / "fixtures"


class Answer(BaseModel):
    answer: str


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text("utf-8"))  # type: ignore[no-any-return]


def request(tier: str = "fast") -> LlmRequest[Answer]:
    return LlmRequest(
        task="demo",
        prompt=RenderedPrompt("demo", 1, "Be brief.", "What is the answer?"),
        output_schema=Answer,
        tier=tier,  # type: ignore[arg-type]
        max_output_tokens=200,
        untrusted_blocks=[UntrustedText("resume", "<<DATA t>>\nJane\n<<END t>>")],
    )


class Server:
    """Records requests and replies with queued (status, json) pairs."""

    def __init__(self, *replies: tuple[int, dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status, body = self.replies.pop(0)
        return httpx2.Response(status, json=body)

    def adapter(
        self, key: str | None = "sk-test-secret", on_rejected: Callable[[], Any] | None = None
    ) -> OpenAiAdapter:
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(self))
        return OpenAiAdapter(
            SecretStr(key) if key else None,
            ModelCatalog.load(),
            http_client=client,
            on_key_rejected=on_rejected,
        )


async def test_constitution_IV_structured_output_parsed() -> None:
    server = Server((200, fixture("response_ok.json")))
    result = await server.adapter().generate(request())

    assert result.value == Answer(answer="42")
    assert result.outcome == "ok"
    assert (result.provider, result.model) == ("openai", "gpt-5.4-mini")
    sent = server.requests[0]
    assert sent.url.path == "/v1/responses"
    body = json.loads(sent.content)
    assert body["model"] == "gpt-5.4-mini"  # the fast tier
    assert body["max_output_tokens"] == 200
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert "Be brief." in json.dumps(body)
    assert "<<DATA t>>" in json.dumps(body)  # the delimited block is sent as data
    assert sent.headers["authorization"] == "Bearer sk-test-secret"


async def test_invalid_schema_output_is_an_error_result() -> None:
    result = (
        await Server((200, fixture("response_invalid_schema.json"))).adapter().generate(request())
    )
    assert result.value is None
    assert result.outcome == "error"
    assert result.error


async def test_usage_mapped() -> None:
    result = await Server((200, fixture("response_ok.json"))).adapter().generate(request())
    usage = result.usage
    assert (usage.input_tokens, usage.cached_input_tokens, usage.output_tokens) == (1200, 200, 30)
    assert not hasattr(usage, "cost_usd")
    assert usage.latency_ms >= 0


async def test_FR030_401_maps_to_key_rejected() -> None:
    rejected: list[bool] = []

    async def on_rejected() -> None:
        rejected.append(True)

    server = Server((401, fixture("error_401.json")))
    with pytest.raises(AiUnavailable) as raised:
        await server.adapter(on_rejected=on_rejected).generate(request())
    assert raised.value.reason == "key_rejected"
    assert rejected == [True]  # provider status gets updated (T024)


async def test_missing_key_pauses_without_network() -> None:
    server = Server()
    with pytest.raises(AiUnavailable) as raised:
        await server.adapter(key=None).generate(request())
    assert raised.value.reason == "key_missing"
    assert server.requests == []


async def test_429_is_retryable() -> None:
    with pytest.raises(RetryableLlmError):
        await Server((429, fixture("error_429.json"))).adapter().generate(request())


async def test_5xx_is_retryable() -> None:
    with pytest.raises(RetryableLlmError):
        await Server((503, {"error": {"message": "overloaded"}})).adapter().generate(request())


async def test_json_mode_fallback() -> None:
    server = Server(
        (400, fixture("error_400_no_structured.json")), (200, fixture("response_ok.json"))
    )
    result = await server.adapter().generate(request())

    assert result.value == Answer(answer="42")
    assert len(server.requests) == 2
    second = json.loads(server.requests[1].content)
    assert second["text"]["format"] == {"type": "json_object"}
    assert "answer" in json.dumps(second["instructions"])  # the schema travels in the prompt


async def test_R3_check_key_uses_models_list() -> None:
    server = Server((200, fixture("models.json")))
    assert await server.adapter().check_key() == "working"
    assert server.requests[0].method == "GET"
    assert server.requests[0].url.path == "/v1/models"


async def test_check_key_rejected_and_unreachable() -> None:
    assert await Server((401, fixture("error_401.json"))).adapter().check_key() == "rejected"
    assert await Server((403, {"error": {"message": "no"}})).adapter().check_key() == "rejected"

    def boom(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(boom))
    adapter = OpenAiAdapter(SecretStr("k"), ModelCatalog.load(), http_client=client)
    assert await adapter.check_key() == "unreachable"
