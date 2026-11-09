"""T017: the title synonym table and its expansion (research R9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.search.application.synonyms_seed import SynonymsError, load_title_synonyms
from hiretitan.search.domain.synonyms import SYNONYMS_PER_ROLE_MAX, expand, normalize_phrase

SEED = Path(__file__).resolve().parents[3] / "seed" / "title_synonyms.yaml"


@pytest.fixture(scope="module")
def table() -> dict[str, tuple[str, ...]]:
    return load_title_synonyms(SEED)


def test_R9_backend_engineer_expands_to_known_synonyms(table: dict[str, tuple[str, ...]]) -> None:
    result = expand("Backend Engineer", table)
    assert result[0] == "backend engineer"
    assert "backend developer" in result
    assert len(result) == len(set(result))


def test_R9_unknown_role_expands_to_itself(table: dict[str, tuple[str, ...]]) -> None:
    assert expand("Chief Llama Wrangler", table) == ("chief llama wrangler",)


@pytest.mark.parametrize(
    "variant", ["BACKEND   ENGINEER", "backend-engineer", " Backend Engineer. "]
)
def test_R9_expansion_is_case_and_punctuation_insensitive(
    table: dict[str, tuple[str, ...]], variant: str
) -> None:
    assert expand(variant, table) == expand("backend engineer", table)


def test_normalize_phrase_keeps_meaningful_symbols() -> None:
    assert normalize_phrase("C++ Developer") == "c++ developer"
    assert normalize_phrase("  Data / ML  Engineer ") == "data ml engineer"


def test_R9_every_role_in_the_shipped_table_is_within_the_limit(
    table: dict[str, tuple[str, ...]],
) -> None:
    assert table
    assert all(len(values) <= SYNONYMS_PER_ROLE_MAX for values in table.values())


def test_R9_table_with_too_many_synonyms_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    many = "\n".join(f"    - s{i}" for i in range(SYNONYMS_PER_ROLE_MAX + 1))
    path.write_text(f"backend engineer:\n{many}\n", "utf-8")
    with pytest.raises(SynonymsError):
        load_title_synonyms(path)
