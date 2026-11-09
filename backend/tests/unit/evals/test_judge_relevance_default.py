"""T028: the default model for relevance judging is backed by the latest eval report."""

from __future__ import annotations

from pathlib import Path

import yaml
from evals.judge_relevance.runner import PRECISION_MIN, RECALL_MIN
from evals.run import REPORTS_DIR

from hiretitan.platform.llm.models import ModelCatalog

PROMPT_META = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "hiretitan"
    / "prompts"
    / "judge_relevance"
    / "v1"
    / "meta.yaml"
)


def _summary_rows(report: Path) -> dict[str, dict[str, str]]:
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


def _percent(text: str) -> float:
    return float(text.rstrip("%")) / 100


def test_defaults_match_latest_judge_relevance_report() -> None:
    reports = sorted(REPORTS_DIR.glob("judge_relevance-*.md"))
    assert reports, "commit an eval report (python -m evals.run judge_relevance)"
    rows = _summary_rows(reports[-1])

    tier = yaml.safe_load(PROMPT_META.read_text(encoding="utf-8"))["tier"]
    row = rows[tier]

    assert row["model"] == ModelCatalog.load().model_for("openai", tier)
    assert _percent(row["precision"]) >= PRECISION_MIN
    assert _percent(row["recall"]) >= RECALL_MIN
    assert row["unusable"] == "0"
    assert row["injection-affected"] == "0"
    assert row["gate"] == "pass"
