"""002m T003: the OpenAI adapter's ``converse`` (Responses API streaming with function tools).

Recorded-shape fixtures are synthetic. The adapter must turn the stream into the port's events,
send the history and tools in the Responses format, and map errors as ``generate`` does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.openai_adapter import OpenAiAdapter
from hiretitan.platform.llm.port import (
    AiUnavailable,
    ChatMessage,
    ConverseEvent,
    ConverseRequest,
    RenderedPrompt,
    RetryableLlmError,
    TextDelta,
    ToolCall,
    ToolSpec,
    TurnEnd,
)

FIXTURES = Path(__file__).parent / "fixtures"

TOOL = ToolSpec(
    name="search_jobs",
    description="Find jobs",
    parameters={"type": "object", "properties": {"title": {"type": "string"}}},
)


def _request() -> ConverseRequest:
    return ConverseRequest(
        task="mikasa_turn",
        prompt=RenderedPrompt("mikasa_chat", 1, "You are Mikasa.", ""),
        messages=[
            ChatMessage(role="person", text="What did I apply to?"),
            ChatMessage(role="mikasa", text="Looking."),
            ChatMessage(
                role="tool_call",
                tool_call_id="call_0",
                tool_name="search_jobs",
                arguments_json="{}",
            ),
            ChatMessage(role="tool_result", tool_call_id="call_0", text="<data>[]</data>"),
            ChatMessage(role="note", text="HireTitan check: rewrite without the number 40%."),
        ],
        tools=[TOOL],
        tier="fast",
        max_output_tokens=800,
    )


def _adapter(
    status: int = 200, *, sse: str | None = None, body: dict[str, Any] | None = None
) -> tuple[OpenAiAdapter, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if sse is not None:
            return httpx2.Response(
                status,
                content=(FIXTURES / sse).read_bytes(),
                headers={"content-type": "text/event-stream"},
            )
        return httpx2.Response(status, json=body or {})

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return OpenAiAdapter(SecretStr("sk-test"), ModelCatalog.load(), http_client=client), seen


async def _collect(adapter: OpenAiAdapter) -> list[ConverseEvent]:
    return [event async for event in adapter.converse(_request())]


async def test_FR023_responses_stream_maps_to_events() -> None:
    adapter, _ = _adapter(sse="converse_text_and_tool.sse")

    events = await _collect(adapter)

    assert events[:3] == [
        TextDelta("Let me "),
        TextDelta("check."),
        ToolCall(id="call_1", name="search_jobs", arguments_json='{"title":"backend"}'),
    ]
    end = events[-1]
    assert isinstance(end, TurnEnd)
    assert (end.provider, end.model, end.outcome) == ("openai", "gpt-5.4-mini", "ok")
    assert (end.usage.input_tokens, end.usage.cached_input_tokens, end.usage.output_tokens) == (
        120,
        20,
        15,
    )


async def test_FR023_history_and_tools_sent_in_responses_format() -> None:
    adapter, seen = _adapter(sse="converse_text_and_tool.sse")

    await _collect(adapter)

    sent = json.loads(seen[0].content)
    assert sent["stream"] is True
    assert sent["instructions"] == "You are Mikasa."
    assert sent["input"] == [
        {"role": "user", "content": "What did I apply to?"},
        {"role": "assistant", "content": "Looking."},
        {"type": "function_call", "call_id": "call_0", "name": "search_jobs", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_0", "output": "<data>[]</data>"},
        {"role": "developer", "content": "HireTitan check: rewrite without the number 40%."},
    ]
    assert sent["tools"] == [
        {
            "type": "function",
            "name": "search_jobs",
            "description": "Find jobs",
            "parameters": {"type": "object", "properties": {"title": {"type": "string"}}},
            "strict": False,
        }
    ]
    assert sent["max_output_tokens"] == 800


async def test_FR024_quota_maps_to_out_of_credit() -> None:
    body = json.loads((FIXTURES / "rate_limit_insufficient_quota.json").read_text("utf-8"))
    adapter, seen = _adapter(429, body=body)

    with pytest.raises(AiUnavailable) as caught:
        await _collect(adapter)
    assert caught.value.reason == "out_of_credit"
    assert caught.value.provider_message
    assert len(seen) == 1


async def test_FR024_rejected_key_and_retryable_errors() -> None:
    rejected, _ = _adapter(401, body={"error": {"message": "bad key"}})
    with pytest.raises(AiUnavailable) as caught:
        await _collect(rejected)
    assert caught.value.reason == "key_rejected"

    busy, _ = _adapter(503, body={"error": {"message": "overloaded"}})
    with pytest.raises(RetryableLlmError):
        await _collect(busy)


async def test_FR024_missing_key_before_any_request() -> None:
    adapter = OpenAiAdapter(None, ModelCatalog.load())
    with pytest.raises(AiUnavailable) as caught:
        await _collect(adapter)
    assert caught.value.reason == "key_missing"


def test_FR024_model_without_tools_reported(tmp_path: Path) -> None:
    catalog_file = tmp_path / "models.yaml"
    catalog_file.write_text(
        "providers:\n"
        "  openai:\n"
        "    tiers: {fast: small-model, strong: big-model}\n"
        "    capabilities:\n"
        "      small-model: [streaming]\n"
        "      big-model: [tools, streaming]\n",
        "utf-8",
    )
    catalog = ModelCatalog.load(catalog_file)

    assert catalog.supports("openai", "fast", "tools") is False
    assert catalog.supports("openai", "strong", "tools") is True
    shipped = ModelCatalog.load()
    assert shipped.supports("openai", "fast", "tools") is True
    assert shipped.supports("openai", "strong", "streaming") is True
