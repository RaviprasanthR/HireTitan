"""judge_relevance v2: a short `role` per job that may only use words from the job's title."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.prompts.judge_relevance.v2.checks import rule_errors

PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"
TITLE = "Senior Backend Engineer (Python) - Remote - Pune"


def out(role: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        decisions=[SimpleNamespace(ref="j1", relevant=True, reason="Fits", role=role)]
    )


def test_latest_judge_prompt_is_v2_and_asks_for_a_role() -> None:
    loaded = PromptRegistry(PROMPTS).load("judge_relevance")
    assert loaded.version.version == 2
    assert "role" in loaded.system


def test_schema_accepts_an_answer_without_a_role() -> None:
    schema = PromptRegistry(PROMPTS).load("judge_relevance").output_schema
    parsed = schema.model_validate({"decisions": [{"ref": "j1", "relevant": True, "reason": "x"}]})
    assert parsed.decisions[0].role is None  # type: ignore[attr-defined]


def test_a_role_made_of_title_words_passes() -> None:
    assert rule_errors(["j1"], [TITLE])(out("Senior Backend Engineer")) == []
    assert rule_errors(["j1"], [TITLE])(out(None)) == []


def test_a_role_with_invented_words_is_reported() -> None:
    errors = rule_errors(["j1"], [TITLE])(out("Staff Backend Architect"))
    assert len(errors) == 1
    assert "Staff" in errors[0]
    assert "Architect" in errors[0]
