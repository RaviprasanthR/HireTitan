"""Versioned prompt registry (architecture §5.4).

Layout: ``<root>/<task>/v<N>/{system.md, user.md.j2, schema.py, meta.yaml}``.
``schema.py`` defines the Pydantic ``Output`` model; ``meta.yaml`` holds the version,
tier, max output tokens and changelog.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import yaml
from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel

from hiretitan.platform.llm.port import RenderedPrompt, Tier

TIERS: Final = ("fast", "strong")
_VERSION_DIR = re.compile(r"v(\d+)")
# Prompts are plain text for a model, not HTML, so autoescaping would corrupt them.
_JINJA = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=False)  # noqa: S701


class PromptNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class PromptVersion:
    name: str
    version: int
    tier: Tier
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class LoadedPrompt:
    version: PromptVersion
    system: str
    user_template: str
    output_schema: type[BaseModel]

    def render(self, **variables: Any) -> RenderedPrompt:
        user = _JINJA.from_string(self.user_template).render(**variables)
        return RenderedPrompt(
            name=self.version.name,
            version=self.version.version,
            system=self.system,
            user=user,
        )


def _load_schema(path: Path) -> type[BaseModel]:
    spec = importlib.util.spec_from_file_location(f"_prompt_schema_{abs(hash(path))}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load prompt schema {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before running, so pydantic can resolve names in postponed annotations.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    schema = getattr(module, "Output", None)
    if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
        raise ValueError(f"{path} must define a Pydantic model named Output")
    return schema


class PromptRegistry:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _latest(self, name: str) -> int:
        folder = self._root / name
        versions = [
            int(m.group(1))
            for child in (folder.iterdir() if folder.is_dir() else [])
            if (m := _VERSION_DIR.fullmatch(child.name))
        ]
        if not versions:
            raise PromptNotFoundError(f"No prompt named {name!r}")
        return max(versions)

    def load(self, name: str, version: int | None = None) -> LoadedPrompt:
        number = self._latest(name) if version is None else version
        folder = self._root / name / f"v{number}"
        if not folder.is_dir():
            raise PromptNotFoundError(f"Prompt {name!r} has no version {number}")
        meta = cast(dict[str, Any], yaml.safe_load((folder / "meta.yaml").read_text("utf-8")))
        if meta.get("version") != number:
            raise ValueError(f"{folder}: meta.yaml version must be {number}")
        if meta.get("tier") not in TIERS:
            raise ValueError(f"{folder}: tier must be one of {TIERS}")
        return LoadedPrompt(
            version=PromptVersion(name, number, meta["tier"], int(meta["max_output_tokens"])),
            system=(folder / "system.md").read_text("utf-8"),
            user_template=(folder / "user.md.j2").read_text("utf-8"),
            output_schema=_load_schema(folder / "schema.py"),
        )
