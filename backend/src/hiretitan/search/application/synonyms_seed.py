"""Read the shipped title synonym table (research R9)."""

from __future__ import annotations

from pathlib import Path

import yaml

from hiretitan.search.domain.synonyms import SYNONYMS_PER_ROLE_MAX, normalize_phrase


class SynonymsError(ValueError):
    """The synonym file is not acceptable."""


def load_title_synonyms(path: Path) -> dict[str, tuple[str, ...]]:
    try:
        raw = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SynonymsError(f"Could not read the title synonyms: {error}") from error
    if not isinstance(raw, dict):
        raise SynonymsError("The title synonyms must map each role to a list of synonyms.")
    table: dict[str, tuple[str, ...]] = {}
    for role, synonyms in raw.items():
        if not isinstance(role, str) or not isinstance(synonyms, list):
            raise SynonymsError(f"{role!r}: expected a role with a list of synonyms.")
        if not all(isinstance(s, str) and normalize_phrase(s) for s in synonyms):
            raise SynonymsError(f"{role!r}: every synonym must be non-empty text.")
        if len(synonyms) > SYNONYMS_PER_ROLE_MAX:
            raise SynonymsError(f"{role!r}: more than {SYNONYMS_PER_ROLE_MAX} synonyms.")
        table[role] = tuple(synonyms)
    return table
