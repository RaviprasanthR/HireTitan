"""T021/T024/T025 wiring: the LLM port is built from settings (no budget guard in front)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.factory import build_llm
from hiretitan.platform.llm.fake import FakeLlm
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


async def test_fake_mode_replays_fixture_scripts(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    (tmp_path / "demo.json").write_text(json.dumps([{"text": "scripted"}]))
    settings = Settings(HIRETITAN_LLM="fake", HIRETITAN_FAKE_LLM_DIR=str(tmp_path))
    built = build_llm(settings, sessions)
    assert isinstance(built.llm, FakeLlm)
    assert (await built.llm.generate(request())).value == Answer(text="scripted")


async def test_openai_mode_without_key_pauses_with_key_missing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    settings = Settings(HIRETITAN_LLM="openai", OPENAI_API_KEY="")
    built = build_llm(settings, sessions)
    with pytest.raises(AiUnavailable) as raised:
        await built.llm.generate(request())
    assert raised.value.reason == "key_missing"
    assert await built.provider_status.check() == "missing"  # no network needed
