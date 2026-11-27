"""002m T013: Mikasa's actions are not exposed outside the app (FR-028).

The catalogue is shaped for 007 ``mcp-access`` to reuse later, but in this feature only Mikasa's
own wiring may import it: no router lists or runs actions directly.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3] / "src" / "hiretitan"
ALLOWED = {Path("assistant_wiring.py")}


def _imports_actions(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("hiretitan.actions")
        ):
            return True
        if isinstance(node, ast.Import) and any(
            alias.name.startswith("hiretitan.actions") for alias in node.names
        ):
            return True
    return False


def test_FR028_actions_not_exposed_outside_app() -> None:
    users = {
        path.relative_to(PACKAGE)
        for path in PACKAGE.rglob("*.py")
        if path.relative_to(PACKAGE).parts[0] != "actions"
        and _imports_actions(path.read_text(encoding="utf-8"))
    }
    assert users == ALLOWED


def test_FR028_check_sees_an_import() -> None:
    assert _imports_actions("from hiretitan.actions.registry import build_catalogue\n")
    assert not _imports_actions("from hiretitan.assistant.api.deps import AssistantApiDeps\n")
