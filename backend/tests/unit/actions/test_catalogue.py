"""002m T029: the catalogue covers what the UI can change (FR-005), each change has a fixed kind
(FR-010), excluded endpoints have no action (FR-016), and nothing can send (US3 scenario 3)."""

from __future__ import annotations

import json
from pathlib import Path

from hiretitan.actions.catalogue import EXCLUDED, EXCLUDED_NAMES
from hiretitan.actions.registry import build_catalogue

OPENAPI = Path(__file__).resolve().parents[3] / "openapi.json"


def _change_endpoints() -> set[str]:
    paths = json.loads(OPENAPI.read_text("utf-8"))["paths"]
    found = set()
    for path, operations in paths.items():
        for method in operations:
            key = f"{method.upper()} {path.removeprefix('/api/v1')}"
            if method != "get" and not key.split(" ", 1)[1].startswith("/assistant"):
                found.add(key)
    return found


def test_FR005_every_ui_endpoint_is_mapped_or_excluded() -> None:
    mirrored = {m for spec in build_catalogue().specs() for m in spec.mirrors}
    missing = _change_endpoints() - mirrored - set(EXCLUDED)
    assert missing == set()


def test_FR010_every_change_action_has_a_fixed_kind() -> None:
    for spec in build_catalogue().specs():
        assert spec.kind in ("read", "small", "risky"), spec.name
        if spec.kind == "risky":
            assert spec.targets is not None, spec.name
            assert spec.card_title, spec.name


def test_FR010_small_actions_have_undo() -> None:
    for spec in build_catalogue().specs():
        if spec.kind == "small":
            assert spec.undo is not None, spec.name
            assert spec.current is not None, spec.name


def test_FR016_excluded_endpoints_have_no_action() -> None:
    catalogue = build_catalogue()
    mirrored = {m for spec in catalogue.specs() for m in spec.mirrors}
    assert mirrored.isdisjoint(EXCLUDED)
    assert {spec.name for spec in catalogue.specs()}.isdisjoint(EXCLUDED_NAMES)


def test_US3_AS3_send_has_no_action() -> None:
    banned = {"send", "submit", "post", "email", "message", "apply"}
    for spec in build_catalogue().specs():
        handler_name = getattr(spec.handler, "__name__", "")
        for name in (spec.name, handler_name):
            words = name.split("_")
            # "draft_referral_message" writes text for the person to send themselves; any other
            # name with one of these words could be a send
            allowed = {"message"} if words[0] == "draft" else set()
            assert (banned - allowed).isdisjoint(words), name
