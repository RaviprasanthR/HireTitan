"""Read the shipped work-area and technology tables, failing fast on a bad file (feature 002i)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from hiretitan.search.domain.rules import AREAS
from hiretitan.search.domain.tech_names import TechName, TechTable
from hiretitan.search.domain.work_areas import AreaEntry, WorkAreaTable

_KINDS = ("language", "framework")


class TablesError(ValueError):
    """A shipped table is not acceptable."""


def _read(path: Path, what: str) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise TablesError(f"Could not read the {what}: {error}") from error
    if not isinstance(raw, dict):
        raise TablesError(f"The {what} must be a mapping.")
    return raw


def _words(value: Any, where: str, *, allow_empty_list: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty_list and not value):
        raise TablesError(f"{where}: expected a list of words.")
    if not all(isinstance(w, str) and w.strip() for w in value):
        raise TablesError(f"{where}: every word must be non-empty text.")
    return tuple(value)


def _key(word: str) -> str:
    return " ".join(word.lower().split())


def load_work_areas(path: Path) -> WorkAreaTable:
    areas = _read(path, "work areas").get("areas")
    if not isinstance(areas, dict):
        raise TablesError("The work areas must map each area to its words.")
    if set(areas) != set(AREAS):
        missing = sorted(set(AREAS) - set(areas))
        unknown = sorted(set(map(str, areas)) - set(AREAS))
        raise TablesError(
            f"The work areas must list every area (missing {missing}, unknown {unknown})."
        )
    table: dict[str, AreaEntry] = {}
    for name, body in areas.items():
        if not isinstance(body, dict):
            raise TablesError(f"{name}: expected signals, avoid_in_titles and compatible.")
        compatible = _words(body.get("compatible"), f"{name}.compatible")
        if not set(compatible) <= set(AREAS) - {name}:
            raise TablesError(f"{name}.compatible: use other known areas only.")
        table[name] = AreaEntry(
            name=name,
            signals=_words(body.get("signals"), f"{name}.signals"),
            avoid_in_titles=_words(body.get("avoid_in_titles"), f"{name}.avoid_in_titles"),
            compatible=compatible,
        )
    return table


def load_tech_names(path: Path) -> TechTable:
    entries = _read(path, "technology names").get("technologies")
    if not isinstance(entries, list) or not entries:
        raise TablesError("The technology names must be a list.")
    seen: set[str] = set()
    table: list[TechName] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TablesError("Each technology needs a name, a kind and aliases.")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise TablesError("Each technology needs a name.")
        kind = entry.get("kind")
        if kind not in _KINDS:
            raise TablesError(f"{name}: kind must be language or framework.")
        aliases = _words(entry.get("aliases"), f"{name}.aliases")
        context = _words(entry.get("context", []), f"{name}.context")
        for word in (name, *aliases):
            if _key(word) in seen:
                raise TablesError(f"{word!r} is listed twice.")
            seen.add(_key(word))
        table.append(TechName(name, kind, aliases, context))
    return tuple(table)


@dataclass(frozen=True, slots=True)
class SeedTables:
    work_areas: WorkAreaTable
    tech_names: TechTable


def load_seed_tables(seed_dir: Path) -> SeedTables:
    """Read both tables, failing at start-up with a clear message when one is wrong."""
    return SeedTables(
        load_work_areas(seed_dir / "work_areas.yaml"), load_tech_names(seed_dir / "tech_names.yaml")
    )


def check_seed_tables(seed_dir: Path) -> None:
    """Fail at start-up, with a clear message, when a shipped table is wrong."""
    load_seed_tables(seed_dir)
