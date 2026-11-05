"""T005: the coverage gate script used by CI (constitution V quality gates).

``scripts/check_coverage.py`` reads coverage.py's JSON report and fails when
``*/domain`` + ``*/application`` code is under 90% or the whole package is
under 80% (statements and branches together, as coverage.py counts them).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_coverage.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_coverage", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file(
    statements: int, covered: int, branches: int = 0, covered_branches: int = 0
) -> dict[str, Any]:
    return {
        "summary": {
            "num_statements": statements,
            "covered_lines": covered,
            "num_branches": branches,
            "covered_branches": covered_branches,
        }
    }


def _report(files: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"files": files}


def test_quality_gate_fails_below_thresholds(gate: ModuleType) -> None:
    report = _report(
        {
            "src/hiretitan/profile/domain/rules.py": _file(100, 85),  # core 85% < 90%
            "src/hiretitan/profile/api/routes.py": _file(100, 60),  # overall 72.5% < 80%
        }
    )
    failures = gate.evaluate(report)
    assert any("domain + application" in f for f in failures)
    assert any("overall" in f for f in failures)


def test_quality_gate_passes_at_thresholds(gate: ModuleType) -> None:
    report = _report(
        {
            "src/hiretitan/profile/domain/rules.py": _file(50, 45, 10, 9),  # 90%
            "src/hiretitan/setup/application/status.py": _file(10, 10),
            "src/hiretitan/profile/api/routes.py": _file(100, 72),
        }
    )
    assert gate.evaluate(report) == []


def test_quality_gate_counts_branches(gate: ModuleType) -> None:
    # lines are fully covered but half the branches are not: 30/40 = 75%
    report = _report({"src/hiretitan/preferences/domain/x.py": _file(20, 20, 20, 10)})
    failures = gate.evaluate(report)
    assert any("domain + application" in f and "75.0%" in f for f in failures)


def test_quality_gate_handles_windows_paths(gate: ModuleType) -> None:
    report = _report({"src\\hiretitan\\profile\\domain\\rules.py": _file(10, 5)})
    assert any("domain + application" in f for f in gate.evaluate(report))


def test_platform_runtime_domain_counts_as_core(gate: ModuleType) -> None:
    report = _report({"src/hiretitan/platform/runtime/domain/run_state.py": _file(10, 5)})
    assert any("domain + application" in f for f in gate.evaluate(report))


def test_main_exit_codes(gate: ModuleType, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_report({"src/hiretitan/a/domain/x.py": _file(10, 1)})))
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_report({"src/hiretitan/a/domain/x.py": _file(10, 10)})))
    assert gate.main([str(bad)]) == 1
    assert gate.main([str(good)]) == 0
