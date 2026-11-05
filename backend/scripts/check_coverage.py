"""Coverage quality gate (constitution V, research R15).

Usage: ``python scripts/check_coverage.py coverage.json``

Reads coverage.py's JSON report (``pytest --cov --cov-report=json``) and exits 1
when ``*/domain`` + ``*/application`` code is below 90% or the whole package is
below 80%. Statements and branches are counted together, as coverage.py does.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CORE_MIN = 90.0
OVERALL_MIN = 80.0
CORE_LAYERS = frozenset({"domain", "application"})


def _counts(summary: Mapping[str, Any]) -> tuple[int, int]:
    covered = int(summary.get("covered_lines", 0)) + int(summary.get("covered_branches", 0))
    total = int(summary.get("num_statements", 0)) + int(summary.get("num_branches", 0))
    return covered, total


def _is_core(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")[:-1]
    return any(part in CORE_LAYERS for part in parts)


def _percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else 100.0 * covered / total


def evaluate(
    report: Mapping[str, Any],
    core_min: float = CORE_MIN,
    overall_min: float = OVERALL_MIN,
) -> list[str]:
    """Return one message per failed threshold (empty list = gate passes)."""
    core_cov = core_total = all_cov = all_total = 0
    for path, data in report.get("files", {}).items():
        covered, total = _counts(data["summary"])
        all_cov += covered
        all_total += total
        if _is_core(path):
            core_cov += covered
            core_total += total

    failures = []
    core = _percent(core_cov, core_total)
    if core < core_min:
        failures.append(f"domain + application coverage {core:.1f}% is below {core_min:.0f}%")
    overall = _percent(all_cov, all_total)
    if overall < overall_min:
        failures.append(f"overall coverage {overall:.1f}% is below {overall_min:.0f}%")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    report_path = Path(args[0] if args else "coverage.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures = evaluate(report)
    for failure in failures:
        print(f"FAIL: {failure}")
    if not failures:
        print("Coverage gate passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
