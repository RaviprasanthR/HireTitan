"""T005: the licence gate script used by CI (constitution VIII, research R15).

``scripts/check_licenses.py`` reads ``pip-licenses --format=json`` output for the
runtime dependencies and fails on any licence outside the allowlist (MIT, BSD,
Apache-2.0, ISC, PSF, MPL-2.0, LGPL), understanding SPDX ``AND``/``OR``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_licenses.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licenses", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "license_text",
    [
        "MIT",
        "MIT License",
        "BSD-3-Clause",
        "BSD License",
        "Apache Software License",
        "Apache-2.0 OR MIT",
        "MIT AND PSF-2.0",
        "MPL-2.0 AND (Apache-2.0 OR MIT)",
        "Mozilla Public License 2.0 (MPL 2.0)",
        "LGPL-3.0-only",
        "ISC",
        "MIT-0",
        "Apache Software License; MIT License",
        "MIT License\n\nCopyright (c) 2022 Someone\n\nPermission is hereby granted, free of charge",
    ],
)
def test_allowed_licences_pass(gate: ModuleType, license_text: str) -> None:
    assert gate.is_allowed(license_text)


@pytest.mark.parametrize(
    "license_text",
    ["GPL-3.0-only", "AGPL-3.0", "MIT AND GPL-2.0", "UNKNOWN", "", "Proprietary", "SSPL-1.0"],
)
def test_disallowed_licences_fail(gate: ModuleType, license_text: str) -> None:
    assert not gate.is_allowed(license_text)


def test_constitution_VIII_licence_gate_fails_on_copyleft(gate: ModuleType) -> None:
    rows = [
        {"Name": "fastapi", "Version": "1", "License": "MIT"},
        {"Name": "pymupdf", "Version": "1", "License": "AGPL-3.0"},
    ]
    assert gate.evaluate(rows) == ["pymupdf 1: AGPL-3.0"]


def test_overrides_are_applied_by_package_name(gate: ModuleType) -> None:
    rows = [{"Name": "regex", "Version": "1", "License": "Apache-2.0 AND CNRI-Python"}]
    assert gate.evaluate(rows) == []
    assert "regex" in gate.OVERRIDES


def test_main_exit_codes(gate: ModuleType, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"Name": "x", "Version": "1", "License": "GPL-3.0"}]))
    good = tmp_path / "good.json"
    good.write_text(json.dumps([{"Name": "x", "Version": "1", "License": "MIT"}]))
    assert gate.main([str(bad)]) == 1
    assert gate.main([str(good)]) == 0
