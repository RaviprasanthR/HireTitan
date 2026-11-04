"""T017: the LLM port types and the scripted FakeLlm."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from hiretitan.platform.llm.fake import FakeLlm, FakeLlmScriptExhaustedError
from hiretitan.platform.llm.port import (
    AiUnavailable,
    LlmRequest,
    LlmResult,
    RenderedPrompt,
    RetryableLlmError,
    UntrustedText,
    Usage,
)


class Answer(BaseModel):
    text: str


def request(task: str = "demo", *, user: str = "hello") -> LlmRequest[Answer]:
    return LlmRequest(
        task=task,
        prompt=RenderedPrompt(name=task, version=1, system="be brief", user=user),
        output_schema=Answer,
        tier="fast",
        max_output_tokens=100,
        untrusted_blocks=[UntrustedText(label="resume", text="<<x>>data<</x>>")],
    )


async def test_records_prompts_and_replays_script() -> None:
    llm = FakeLlm([Answer(text="one"), {"text": "two"}])

    first = await llm.generate(request(user="q1"))
    second = await llm.generate(request(user="q2"))

    assert isinstance(first, LlmResult)
    assert first.value == Answer(text="one")
    assert first.outcome == "ok"
    assert second.value == Answer(text="two")  # a dict is validated into the schema
    assert [call.prompt.user for call in llm.calls] == ["q1", "q2"]
    assert llm.calls[0].untrusted_blocks[0].label == "resume"
    assert llm.calls[0].tier == "fast"
    assert first.provider == "fake"
    assert first.usage == Usage()


async def test_scripted_exception_is_raised() -> None:
    llm = FakeLlm([AiUnavailable("key_missing"), RetryableLlmError("429")])
    with pytest.raises(AiUnavailable):
        await llm.generate(request())
    with pytest.raises(RetryableLlmError):
        await llm.generate(request())
    assert len(llm.calls) == 2  # the prompt is recorded even when the call fails


async def test_invalid_payload_is_an_error_result_not_a_crash() -> None:
    llm = FakeLlm([{"wrong": 1}])
    result = await llm.generate(request())
    assert result.value is None
    assert result.outcome == "error"
    assert result.error


async def test_exhausted_script_fails_loudly() -> None:
    llm = FakeLlm([])
    with pytest.raises(FakeLlmScriptExhaustedError):
        await llm.generate(request())


async def test_scripts_loaded_from_a_fixture_directory(tmp_path: Path) -> None:
    (tmp_path / "demo.json").write_text(json.dumps([{"text": "a"}, {"text": "b"}]))
    (tmp_path / "other.json").write_text(json.dumps([{"text": "z"}]))
    llm = FakeLlm.from_directory(tmp_path)

    assert (await llm.generate(request("demo"))).value == Answer(text="a")
    assert (await llm.generate(request("other"))).value == Answer(text="z")
    assert (await llm.generate(request("demo"))).value == Answer(text="b")


def test_ai_unavailable_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError):
        AiUnavailable("because")
