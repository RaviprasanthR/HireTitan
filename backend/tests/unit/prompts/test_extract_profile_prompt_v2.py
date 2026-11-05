"""The extract_profile v2 prompt: v1 plus ``looks_like_resume`` so non-resumes can be rejected."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.platform.llm.prompts import PromptRegistry

PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    return PromptRegistry(PROMPTS)


def test_the_latest_version_is_two_on_the_fast_tier(registry: PromptRegistry) -> None:
    version = registry.load("extract_profile").version

    assert (version.version, version.tier) == (2, "fast")


def test_schema_requires_looks_like_resume(registry: PromptRegistry) -> None:
    schema = registry.load("extract_profile").output_schema

    assert schema.model_json_schema()["properties"]["looks_like_resume"] == {
        "title": "Looks Like Resume",
        "type": "boolean",
    }
    assert "looks_like_resume" in schema.model_json_schema()["required"]


def test_system_prompt_says_what_is_not_a_resume(registry: PromptRegistry) -> None:
    system = registry.load("extract_profile").system

    assert "looks_like_resume" in system
    assert "relieving" in system
    assert "never instructions" in system  # the injection defence is still there


def test_v1_is_kept_for_history(registry: PromptRegistry) -> None:
    v1 = registry.load("extract_profile", version=1).output_schema

    assert "looks_like_resume" not in v1.model_json_schema()["properties"]
