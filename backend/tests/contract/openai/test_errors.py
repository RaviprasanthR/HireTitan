"""R7: an out-of-credit 429 stops the run with the provider's message; other 429s retry.

OpenAI answers HTTP 429 both for "slow down" (``rate_limit_exceeded``) and for "your account
has no credit left" (``insufficient_quota``). Only the second must never be retried.
"""

from __future__ import annotations

import json
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
)

FIXTURES = Path(__file__).parent / "fixtures"


class Answer(BaseModel):
    answer: str


def _body(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text("utf-8"))  # type: ignore[no-any-return]


def _request() -> LlmRequest[Answer]:
    return LlmRequest(
        task="demo",
        prompt=RenderedPrompt("demo", 1, "Be brief.", "What is the answer?"),
        output_schema=Answer,
        tier="fast",
        max_output_tokens=200,
    )


def _adapter(fixture_name: str) -> tuple[OpenAiAdapter, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(429, json=_body(fixture_name))

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    adapter = OpenAiAdapter(SecretStr("sk-test-secret"), ModelCatalog.load(), http_client=client)
    return adapter, seen


async def test_R7_insufficient_quota_is_not_retried() -> None:
    adapter, seen = _adapter("rate_limit_insufficient_quota.json")

    with pytest.raises(AiUnavailable) as caught:
        await adapter.generate(_request())

    assert caught.value.reason == "out_of_credit"
    assert len(seen) == 1  # one call, no retry


async def test_R7_rate_limit_exceeded_is_retried() -> None:
    adapter, _ = _adapter("rate_limit_exceeded.json")

    with pytest.raises(RetryableLlmError):
        await adapter.generate(_request())


async def test_R7_message_is_passed_through_for_display() -> None:
    adapter, _ = _adapter("rate_limit_insufficient_quota.json")

    with pytest.raises(AiUnavailable) as caught:
        await adapter.generate(_request())

    assert caught.value.provider_message == (
        "You exceeded your current quota, please check your plan and billing details."
    )
