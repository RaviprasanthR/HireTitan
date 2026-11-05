"""T018: the versioned prompt registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.platform.llm.prompts import PromptNotFoundError, PromptRegistry, PromptVersion

SCHEMA = """
from pydantic import BaseModel


class Output(BaseModel):
    answer: str
"""


def write_prompt(
    root: Path, name: str, version: int, *, tier: str = "fast", user: str = "Hi {{ who }}"
) -> None:
    folder = root / name / f"v{version}"
    folder.mkdir(parents=True)
    (folder / "system.md").write_text(f"System for {name} v{version}")
    (folder / "user.md.j2").write_text(user)
    (folder / "schema.py").write_text(SCHEMA)
    (folder / "meta.yaml").write_text(
        f"version: {version}\ntier: {tier}\nmax_output_tokens: 1500\nchangelog: first\n"
    )


def test_loads_versioned_prompt(tmp_path: Path) -> None:
    write_prompt(tmp_path, "extract_profile", 1)
    write_prompt(tmp_path, "extract_profile", 2, tier="strong")
    registry = PromptRegistry(tmp_path)

    latest = registry.load("extract_profile")
    assert latest.version == PromptVersion("extract_profile", 2, "strong", 1500)
    assert registry.load("extract_profile", version=1).version.tier == "fast"

    rendered = latest.render(who="Jane")
    assert (rendered.name, rendered.version) == ("extract_profile", 2)
    assert rendered.system == "System for extract_profile v2"
    assert rendered.user == "Hi Jane"
    assert latest.output_schema.model_validate({"answer": "x"}).answer == "x"


def test_missing_prompt_or_version_is_rejected(tmp_path: Path) -> None:
    write_prompt(tmp_path, "extract_profile", 1)
    registry = PromptRegistry(tmp_path)
    with pytest.raises(PromptNotFoundError):
        registry.load("nope")
    with pytest.raises(PromptNotFoundError):
        registry.load("extract_profile", version=9)


def test_unfilled_template_variable_is_an_error(tmp_path: Path) -> None:
    write_prompt(tmp_path, "extract_profile", 1)
    with pytest.raises(Exception, match="who"):
        PromptRegistry(tmp_path).load("extract_profile").render()


def test_meta_must_match_folder_version_and_known_tier(tmp_path: Path) -> None:
    write_prompt(tmp_path, "a", 1)
    (tmp_path / "a" / "v1" / "meta.yaml").write_text(
        "version: 2\ntier: fast\nmax_output_tokens: 10\n"
    )
    with pytest.raises(ValueError, match="version"):
        PromptRegistry(tmp_path).load("a")
    write_prompt(tmp_path, "b", 1, tier="huge")
    with pytest.raises(ValueError, match="tier"):
        PromptRegistry(tmp_path).load("b")


NESTED_SCHEMA = """from __future__ import annotations

from pydantic import BaseModel


class Inner(BaseModel):
    value: int


class Output(BaseModel):
    inner: Inner
"""


def test_schema_with_nested_models_and_postponed_annotations_loads(tmp_path: Path) -> None:
    write_prompt(tmp_path, "nested", 1)
    (tmp_path / "nested" / "v1" / "schema.py").write_text(NESTED_SCHEMA)
    schema = PromptRegistry(tmp_path).load("nested").output_schema
    assert schema.model_validate({"inner": {"value": 3}}).inner.value == 3
