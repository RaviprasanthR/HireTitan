"""T022: the validation chain (schema, business rules, task check, safety) with one repair."""

from __future__ import annotations

from pydantic import BaseModel

from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.infra.calls_repo import LlmCallRecord
from hiretitan.platform.llm.port import LlmRequest, RenderedPrompt
from hiretitan.platform.llm.validation import Dropped, TaskSpec, ValidatedLlm


class Answer(BaseModel):
    text: str


def request() -> LlmRequest[Answer]:
    return LlmRequest(
        task="demo",
        prompt=RenderedPrompt("demo", 3, "system", "question"),
        output_schema=Answer,
        tier="fast",
        max_output_tokens=100,
    )


def non_empty(value: Answer) -> list[str]:
    return [] if value.text.strip() else ["text must not be empty"]


class Recorder:
    def __init__(self) -> None:
        self.calls: list[LlmCallRecord] = []

    async def __call__(self, call: LlmCallRecord) -> None:
        self.calls.append(call)


FALLBACK = Answer(text="fallback")
SPEC = TaskSpec(rules=non_empty, fallback=lambda: FALLBACK)


async def test_valid_first_answer_is_ok() -> None:
    recorder = Recorder()
    llm = FakeLlm([Answer(text="fine")])
    result = await ValidatedLlm(llm, recorder, provider="fake").run(request(), SPEC)
    assert (result.outcome, result.value) == ("ok", Answer(text="fine"))
    assert len(llm.calls) == 1
    assert [c.outcome for c in recorder.calls] == ["ok"]


async def test_constitution_IV_one_repair_then_fallback() -> None:
    recorder = Recorder()
    llm = FakeLlm([Answer(text=" "), {"wrong": 1}, Answer(text="never reached")])
    result = await ValidatedLlm(llm, recorder, provider="fake").run(request(), SPEC)

    assert result.outcome == "fallback"
    assert result.value == FALLBACK
    assert len(llm.calls) == 2  # exactly one repair, never a third call
    assert [c.outcome for c in recorder.calls] == ["error", "fallback"]  # each attempt logged


async def test_repaired_outcome() -> None:
    recorder = Recorder()
    llm = FakeLlm([Answer(text=""), Answer(text="better")])
    result = await ValidatedLlm(llm, recorder, provider="fake").run(request(), SPEC)

    assert (result.outcome, result.value) == ("repaired", Answer(text="better"))
    repair_prompt = llm.calls[1].prompt
    assert "text must not be empty" in repair_prompt.user  # the error list goes back
    assert repair_prompt.user.startswith("question")
    assert repair_prompt.version == 3
    assert [c.outcome for c in recorder.calls] == ["error", "repaired"]
    assert recorder.calls[0].prompt_version == "3"


async def test_schema_failure_is_repaired_with_the_parse_error() -> None:
    llm = FakeLlm([{"wrong": 1}, Answer(text="ok now")])
    result = await ValidatedLlm(llm, Recorder(), provider="fake").run(request(), SPEC)
    assert result.outcome == "repaired"
    assert "text" in llm.calls[1].prompt.user


async def test_task_check_keeps_value_and_reports_dropped_items() -> None:
    def check(value: Answer) -> tuple[Answer, list[Dropped]]:
        return Answer(text=value.text.replace("invented", "").strip()), [
            Dropped(path="text", reason="not in the profile", item="invented")
        ]

    spec = TaskSpec(rules=non_empty, check=check, fallback=lambda: FALLBACK)
    llm = FakeLlm([Answer(text="real invented")])
    result = await ValidatedLlm(llm, Recorder(), provider="fake").run(request(), spec)
    assert result.value == Answer(text="real")
    assert result.dropped == [Dropped("text", "not in the profile", "invented")]
    assert result.outcome == "ok"


async def test_safety_strips_unexpected_urls() -> None:
    llm = FakeLlm(
        [Answer(text="See https://evil.example/x and mail bad@evil.example or https://ok.example")]
    )
    spec = TaskSpec(
        rules=non_empty, fallback=lambda: FALLBACK, allowed_links=frozenset({"https://ok.example"})
    )
    result = await ValidatedLlm(llm, Recorder(), provider="fake").run(request(), spec)

    assert result.value is not None
    assert "evil.example" not in result.value.text
    assert "https://ok.example" in result.value.text
    assert {d.item for d in result.dropped} == {"https://evil.example/x", "bad@evil.example"}
    assert result.outcome == "ok"


async def test_refused_answer_goes_straight_to_fallback() -> None:
    from hiretitan.platform.llm.port import LlmResult, Usage

    class Refuser:
        calls = 0

        async def generate(self, req: LlmRequest[Answer]) -> LlmResult[Answer]:
            Refuser.calls += 1
            return LlmResult(None, "refused", Usage(), "fake", "m", error="refused")

    result = await ValidatedLlm(Refuser(), Recorder(), provider="fake").run(request(), SPEC)  # type: ignore[arg-type]
    assert result.outcome == "fallback"
    assert Refuser.calls == 1
