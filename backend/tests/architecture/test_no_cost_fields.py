"""Feature 002d: HireTitan has no AI cost, budget or spend anywhere (SC-003, SC-004)."""

from __future__ import annotations

import json
import re
from pathlib import Path

OPENAPI = Path(__file__).resolve().parents[2] / "openapi.json"
FORBIDDEN = re.compile(r"cost|budget|spend|spent|price", re.IGNORECASE)


def _property_names(node: object) -> list[str]:
    names: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                names.extend(value)
            names.extend(_property_names(value))
    elif isinstance(node, list):
        for item in node:
            names.extend(_property_names(item))
    return names


def test_SC003_no_cost_budget_or_spend_field_in_the_api() -> None:
    schema = json.loads(OPENAPI.read_text(encoding="utf-8"))

    offenders = sorted({n for n in _property_names(schema) if FORBIDDEN.search(n)})

    assert offenders == []


def test_SC003_no_settings_endpoint() -> None:
    schema = json.loads(OPENAPI.read_text(encoding="utf-8"))

    assert [p for p in schema["paths"] if p.endswith("/settings")] == []
