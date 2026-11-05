"""T067: the default model for profile extraction is backed by the latest eval report."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from evals.run import REPORTS_DIR, SC003_TARGET, SC007_MAX_USD

from hiretitan.platform.llm.models import ModelCatalog

PROMPT_META = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "hiretitan"
    / "prompts"
    / "extract_profile"
    / "v1"
    / "meta.yaml"
)


def _summary_rows(report: Path) -> dict[str, dict[str, str]]:
    """Rows of the report's first table, keyed by tier."""
    rows: dict[str, dict[str, str]] = {}
    header: list[str] = []
    for line in report.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("| model") and not header:
            header = cells
        elif header and line.startswith("|") and not set(line) <= set("|- "):
            row = dict(zip(header, cells, strict=False))
            rows[row["tier"]] = row
        elif header and not line.startswith("|"):
            break
    return rows


def test_defaults_match_latest_eval_report() -> None:
    reports = sorted(REPORTS_DIR.glob("extract_profile-*.md"))
    assert reports, "commit an eval report (python -m evals.run extract_profile)"
    rows = _summary_rows(reports[-1])

    tier = yaml.safe_load(PROMPT_META.read_text(encoding="utf-8"))["tier"]
    row = rows[tier]

    assert row["model"] == ModelCatalog.load().model_for("openai", tier)
    assert Decimal(row["recall"].rstrip("%")) / 100 >= Decimal(str(SC003_TARGET))
    assert Decimal(row["cost / resume"].lstrip("$")) < SC007_MAX_USD
    assert row["unusable"] == "0"
