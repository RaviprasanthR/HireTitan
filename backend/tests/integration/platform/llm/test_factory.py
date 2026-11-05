"""T021/T024/T025 wiring: the LLM port is built from settings and always wrapped in the guard."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.budget import BudgetGuard
from hiretitan.platform.llm.factory import build_llm
from hiretitan.platform.llm.port import AiUnavailable, LlmRequest, RenderedPrompt


class Answer(BaseModel):
    text: str


def request() -> LlmRequest[Answer]:
    return LlmRequest(
        task="demo",
        prompt=RenderedPrompt("demo", 1, "system", "user"),
        output_schema=Answer,
        tier="fast",
        max_output_tokens=100,
    )


async def cap(value: str):  # type: ignore[no-untyped-def]
    return Decimal(value)


async def test_fake_mode_replays_fixture_scripts(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    (tmp_path / "demo.json").write_text(json.dumps([{"text": "scripted"}]))
    settings = Settings(HIRETITAN_LLM="fake", HIRETITAN_FAKE_LLM_DIR=str(tmp_path))
    built = build_llm(settings, sessions, lambda: cap("25"), FakeClock())
    assert isinstance(built.llm, BudgetGuard)
    assert (await built.llm.generate(request())).value == Answer(text="scripted")


async def test_openai_mode_enforces_the_budget_before_the_network(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(HIRETITAN_LLM="openai", OPENAI_API_KEY="sk-never-sent")
    built = build_llm(settings, sessions, lambda: cap("0"), FakeClock())
    # A cap of 0 blocks the call in the guard, so the adapter (and the network) is never reached.
    with pytest.raises(AiUnavailable) as raised:
        await built.llm.generate(request())
    assert raised.value.reason == "budget_reached"


async def test_openai_mode_without_key_pauses_with_key_missing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(HIRETITAN_LLM="openai", OPENAI_API_KEY="")
    built = build_llm(settings, sessions, lambda: cap("25"), FakeClock())
    with pytest.raises(AiUnavailable) as raised:
        await built.llm.generate(request())
    assert raised.value.reason == "key_missing"
    assert await built.provider_status.check() == "missing"  # no network needed
