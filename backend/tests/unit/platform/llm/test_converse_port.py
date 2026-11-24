"""002m T002: the streaming, tool-calling ``converse`` port and the scripted fake (research R1)."""

from __future__ import annotations

import pytest

from hiretitan.platform.llm.fake import FakeLlm, FakeLlmScriptExhaustedError
from hiretitan.platform.llm.port import (
    AiUnavailable,
    ChatMessage,
    ConverseEvent,
    ConversePort,
    ConverseRequest,
    RenderedPrompt,
    TextDelta,
    ToolCall,
    ToolSpec,
    TurnEnd,
    Usage,
)

LOOKUP = ToolSpec(
    name="search_jobs",
    description="Find jobs",
    parameters={"type": "object", "properties": {"title": {"type": "string"}}},
)


def request(task: str = "mikasa_turn", text: str = "what did I apply to?") -> ConverseRequest:
    return ConverseRequest(
        task=task,
        prompt=RenderedPrompt(name="mikasa_chat", version=1, system="You are Mikasa.", user=""),
        messages=[ChatMessage(role="person", text=text)],
        tools=[LOOKUP],
        tier="fast",
        max_output_tokens=800,
    )


async def collect(llm: ConversePort, req: ConverseRequest) -> list[ConverseEvent]:
    return [event async for event in llm.converse(req)]


async def test_FR023_converse_streams_text_and_tool_calls() -> None:
    llm = FakeLlm()
    llm.add_turn(
        TextDelta("Let me look"),
        TextDelta("."),
        ToolCall(id="c1", name="search_jobs", arguments_json='{"title": "backend"}'),
    )

    events = await collect(llm, request())

    assert events[:3] == [
        TextDelta("Let me look"),
        TextDelta("."),
        ToolCall(id="c1", name="search_jobs", arguments_json='{"title": "backend"}'),
    ]
    assert isinstance(events[-1], TurnEnd)  # always last, added when the script leaves it out
    assert llm.converse_calls[0].tools == [LOOKUP]
    assert llm.converse_calls[0].messages[0].text == "what did I apply to?"


async def test_FR023_turn_end_carries_usage_for_logging() -> None:
    llm = FakeLlm()
    llm.add_turn(TextDelta("Hi"))
    llm.add_turn(
        TextDelta("Again"),
        TurnEnd(Usage(input_tokens=12, output_tokens=3), "fake", "fake-model", "ok"),
    )

    first = await collect(llm, request())
    second = await collect(llm, request())

    end = first[-1]
    assert isinstance(end, TurnEnd)
    assert (end.provider, end.model, end.outcome) == ("fake", "fake-model", "ok")
    assert second[-1] == TurnEnd(
        Usage(input_tokens=12, output_tokens=3), "fake", "fake-model", "ok"
    )
    assert sum(isinstance(e, TurnEnd) for e in second) == 1


async def test_FR024_out_of_credit_raises_ai_unavailable() -> None:
    llm = FakeLlm()
    llm.add_turn(AiUnavailable("out_of_credit", "You exceeded your current quota"))

    with pytest.raises(AiUnavailable) as raised:
        await collect(llm, request())
    assert raised.value.reason == "out_of_credit"
    assert raised.value.provider_message == "You exceeded your current quota"


async def test_FR024_missing_key_raises_before_the_script(tmp_path: object) -> None:
    from pathlib import Path

    folder = Path(str(tmp_path))
    (folder / "key_status").write_text("missing", "utf-8")
    llm = FakeLlm(control_dir=folder)
    llm.add_turn(TextDelta("never"))

    with pytest.raises(AiUnavailable) as raised:
        await collect(llm, request())
    assert raised.value.reason == "key_missing"


async def test_FR023_turns_are_kept_per_task_and_dicts_are_read() -> None:
    llm = FakeLlm()
    llm.add_turn({"text": "other task"}, task="other")
    llm.add_turn(
        {"text": "Done "},
        {"tool_call": {"id": "c9", "name": "search_jobs", "arguments": {"title": "x"}}},
        task="mikasa_turn",
    )

    events = await collect(llm, request())

    assert events[0] == TextDelta("Done ")
    assert events[1] == ToolCall(id="c9", name="search_jobs", arguments_json='{"title": "x"}')


async def test_FR023_running_out_of_turns_fails_loudly() -> None:
    with pytest.raises(FakeLlmScriptExhaustedError):
        await collect(FakeLlm(), request())


async def test_FR023_generate_and_converse_scripts_are_separate() -> None:
    llm = FakeLlm([{"text": "for generate"}])
    llm.add_turn(TextDelta("for converse"))

    events = await collect(llm, request())

    assert events[0] == TextDelta("for converse")
    assert len(llm.calls) == 0  # generate was not touched


async def test_FR023_turns_can_be_scripted_in_a_file_and_appended_later(tmp_path: object) -> None:
    """End-to-end runs script chat turns in <task>.turns.json, read again on every call."""
    import json
    from pathlib import Path

    folder = Path(str(tmp_path))
    file = folder / "mikasa_turn.turns.json"
    file.write_text(json.dumps([[{"text": "first"}]]), "utf-8")
    (folder / "mikasa_topic.json").write_text(
        json.dumps([{"on_topic": True, "reason": "x"}]), "utf-8"
    )
    llm = FakeLlm.from_directory(folder)

    first = await collect(llm, request())
    file.write_text(
        json.dumps(
            [
                [{"text": "first"}],
                [{"tool_call": {"id": "c1", "name": "search_jobs", "arguments": {}}}],
            ]
        ),
        "utf-8",
    )
    second = await collect(llm, request())

    assert first[0] == TextDelta("first")
    assert second[0] == ToolCall(id="c1", name="search_jobs", arguments_json="{}")
    with pytest.raises(FakeLlmScriptExhaustedError):
        await collect(llm, request())  # the cursor moved on: nothing left
