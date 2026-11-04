"""T043: the extract_profile v1 prompt and its output schema (FR-008a, constitution III/IV)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.untrusted.delimit import delimit

PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"


@pytest.fixture(scope="module")
def prompt():  # type: ignore[no-untyped-def]
    return PromptRegistry(PROMPTS).load("extract_profile", version=1)


def walk(node: Any, path: str = ""):  # type: ignore[no-untyped-def]
    """Every (path, schema-node) pair in a JSON schema, following $defs and properties."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]")


def property_names(schema: dict[str, Any]) -> set[str]:
    return {
        name
        for _, node in walk(schema)
        if isinstance(node, dict) and "properties" in node
        for name in node["properties"]
    }


def test_registry_loads_version_one_with_the_agreed_settings(prompt) -> None:  # type: ignore[no-untyped-def]
    version = prompt.version
    assert (version.name, version.version, version.tier, version.max_output_tokens) == (
        "extract_profile",
        1,
        "fast",
        4000,
    )


def test_FR008a_schema_has_no_email_phone_links(prompt) -> None:  # type: ignore[no-untyped-def]
    names = property_names(prompt.output_schema.model_json_schema())
    assert names.isdisjoint({"email", "phone", "links", "link", "url", "id", "website"})
    assert {"name", "location"} <= names  # the contact keeps only what is not masked


def test_schema_is_strict_and_bounded(prompt) -> None:  # type: ignore[no-untyped-def]
    schema = prompt.output_schema.model_json_schema()
    objects = [n for _, n in walk(schema) if isinstance(n, dict) and "properties" in n]
    assert objects
    for node in objects:
        assert node.get("additionalProperties") is False, node.get("title")
    for path, node in walk(schema):
        if not isinstance(node, dict):
            continue
        if node.get("type") == "string" and "enum" not in node:
            assert "maxLength" in node, path
        if node.get("type") == "array":
            assert "maxItems" in node, path


def test_schema_bounds_match_the_profile_limits(prompt) -> None:  # type: ignore[no-untyped-def]
    model = prompt.output_schema
    ok: dict[str, Any] = {
        "contact": {"name": "A", "location": None},
        "headline": None,
        "summary": None,
        "experience": [],
        "education": [],
        "skills": ["s"],
        "projects": [],
        "certifications": [],
    }
    model.model_validate(ok)
    for field, bad in [
        ("skills", [f"s{i}" for i in range(151)]),
        ("skills", ["x" * 81]),
        ("headline", "x" * 201),
        ("summary", "x" * 2001),
        ("experience", [{"employer": "e", "title": "t"}] * 41),
    ]:
        with pytest.raises(ValueError):
            model.model_validate({**ok, field: bad})


def test_unknown_fields_are_rejected(prompt) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        prompt.output_schema.model_validate(
            {"contact": {"name": "A", "email": "a@example.com"}, "skills": []}
        )


def test_system_prompt_forbids_following_instructions(prompt) -> None:  # type: ignore[no-untyped-def]
    system = prompt.system.lower()
    assert "data block" in system
    assert "never follow" in system or "do not follow" in system
    assert "instructions" in system
    assert "verbatim" in system
    assert "[[" in prompt.system  # placeholders are explained
    assert "not stated" in system or "omit" in system


def test_user_template_renders_the_delimited_block(prompt) -> None:  # type: ignore[no-untyped-def]
    block = delimit("resume", "Jane Example\nPython")
    rendered = prompt.render(resume_block=block.text)
    assert block.text in rendered.user
    assert rendered.system == prompt.system
    assert (rendered.name, rendered.version) == ("extract_profile", 1)


def test_the_template_needs_the_block(prompt) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(Exception, match="resume_block"):
        prompt.render()
