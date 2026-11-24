"""002m T011: every private read in the catalogue can only answer with refs and labels (FR-022).

Checked on the handlers' declared return types, so a new private action that returns a
``ReadResult`` (which may carry any field) fails here before it is ever called.
"""

from __future__ import annotations

import typing

from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionError, PrivateResult, ReadResult


def _returns(handler: object) -> set[object]:
    hints = typing.get_type_hints(handler)
    answer = hints["return"]
    return set(typing.get_args(answer)) or {answer}


def test_FR022_private_actions_return_refs_and_labels_only() -> None:
    private = [spec for spec in build_catalogue().specs() if spec.private and spec.kind == "read"]
    assert {spec.name for spec in private} >= {
        "list_contacts",
        "find_contact",
        "get_company_note",
        "get_interview",
        "list_rounds",
        "list_resume_files",
    }
    for spec in private:
        returns = _returns(spec.handler)
        assert ReadResult not in returns, spec.name
        assert returns <= {PrivateResult, ActionError}, spec.name


def test_FR022_public_reads_are_not_marked_private_by_mistake() -> None:
    for spec in build_catalogue().specs():
        if spec.kind == "read" and not spec.private:
            assert PrivateResult not in _returns(spec.handler), spec.name
