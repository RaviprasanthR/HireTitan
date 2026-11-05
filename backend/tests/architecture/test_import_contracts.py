"""Constitution VI: layer and module boundaries are enforced by import-linter.

The contracts live in ``backend/.importlinter``. The first test checks the real
package; the planted-violation tests copy the package to a temp dir, add one
offending module per contract and check that ``lint-imports`` fails, so a
contract that silently stops matching anything is caught.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
CONFIG = BACKEND / ".importlinter"
LINT_IMPORTS = Path(sys.executable).parent / (
    "lint-imports.exe" if os.name == "nt" else "lint-imports"
)


def _run_lint_imports(src_root: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(src_root)}
    return subprocess.run(
        [str(LINT_IMPORTS), "--config", str(CONFIG), "--no-cache", "--no-logo"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_constitution_VI_import_contracts_hold() -> None:
    result = _run_lint_imports(BACKEND / "src", BACKEND)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 broken" in result.stdout


# violation name -> {path inside the hiretitan package: source}
PLANTED_VIOLATIONS: dict[str, dict[str, str]] = {
    "domain_imports_framework": {"profile/domain/bad.py": "import fastapi\n"},
    "domain_imports_runtime": {
        # the runtime package may not exist yet, so the plant brings its own
        "platform/runtime/__init__.py": "",
        "preferences/domain/bad.py": "import hiretitan.platform.runtime\n",
    },
    "lower_layer_imports_higher": {"profile/domain/bad.py": "import hiretitan.profile.api\n"},
    "infra_imports_api": {"setup/infra/bad.py": "import hiretitan.setup.api\n"},
    "module_bypasses_application": {
        "profile/application/bad.py": "import hiretitan.preferences.infra\n",
    },
    "platform_imports_feature": {"platform/bad.py": "import hiretitan.profile\n"},
}


@pytest.mark.parametrize("violation", sorted(PLANTED_VIOLATIONS))
def test_constitution_VI_planted_violation_fails(violation: str, tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    shutil.copytree(
        BACKEND / "src" / "hiretitan",
        src_root / "hiretitan",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for rel_path, source in PLANTED_VIOLATIONS[violation].items():
        target = src_root / "hiretitan" / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(source, encoding="utf-8")

    result = _run_lint_imports(src_root, tmp_path)

    assert result.returncode != 0, f"{violation} was not caught:\n{result.stdout}"
    assert "BROKEN" in result.stdout
