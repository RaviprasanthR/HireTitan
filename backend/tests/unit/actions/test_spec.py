"""002m T006: action types, refs and the catalogue (R3, R5; FR-010, FR-016, FR-022)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, Field

from hiretitan.actions.catalogue import EXCLUDED, Catalogue, ExcludedActionError
from hiretitan.actions.refs import Ref, label_contact, label_round
from hiretitan.actions.spec import (
    ActionSpec,
    InvalidActionSpecError,
    PrivateItem,
    PrivateResult,
    ReadResult,
    model_facing,
    to_tool_spec,
)

JOB_ID = UUID("0190a1b2-0000-7000-8000-000000000001")


class JobArgs(BaseModel):
    job: str = Field(description="A job ref, like job:<id>")
    applied_on: str | None = None


async def _handler(ctx: Any, args: Any) -> Any:
    return None


async def _undo(ctx: Any, change: Any) -> None:
    return None


async def _current(ctx: Any, target_id: UUID) -> dict[str, Any] | None:
    return None


async def _targets(ctx: Any, args: Any) -> dict[str, dict[str, Any]]:
    return {}


def _spec(kind: str, **extra: Any) -> ActionSpec:
    return ActionSpec(
        name=extra.pop("name", "mark_applied"),
        description="Mark a job as applied",
        args=JobArgs,
        kind=kind,  # type: ignore[arg-type]
        handler=_handler,
        **extra,
    )


def test_FR010_kind_is_part_of_the_spec() -> None:
    spec = _spec("small", undo=_undo, current=_current)
    tool = to_tool_spec(spec)

    assert tool.name == "mark_applied"
    assert tool.description == "Mark a job as applied"
    assert tool.parameters["properties"]["job"]["description"] == "A job ref, like job:<id>"
    # the model is given the arguments only; whether a card is needed is not its to choose
    assert "kind" not in tool.parameters["properties"]
    with pytest.raises(AttributeError):
        spec.kind = "read"  # type: ignore[misc]


def test_FR010_small_needs_undo_risky_needs_targets() -> None:
    with pytest.raises(InvalidActionSpecError):
        _spec("small")  # no undo
    with pytest.raises(InvalidActionSpecError):
        _spec("small", undo=_undo)  # no way to read the current fields for EC-16
    with pytest.raises(InvalidActionSpecError):
        _spec("risky")  # no targets to fingerprint
    with pytest.raises(InvalidActionSpecError):
        _spec("read", undo=_undo)  # a read changes nothing
    with pytest.raises(InvalidActionSpecError):
        _spec("read", name="Bad Name")
    assert _spec("risky", targets=_targets).kind == "risky"
    assert _spec("read", name="search_jobs").kind == "read"


def test_FR022_private_result_has_only_ref_and_label() -> None:
    private = PrivateResult(
        items=[PrivateItem(ref=f"contact:{JOB_ID}", label="a contact at Acme")], total=1
    )
    assert model_facing(private) == {
        "items": [{"ref": f"contact:{JOB_ID}", "label": "a contact at Acme"}],
        "total": 1,
    }
    with pytest.raises(TypeError):
        PrivateItem(ref=f"contact:{JOB_ID}", label="x", name="Quillon")  # type: ignore[call-arg]

    read = ReadResult(items=[{"ref": f"job:{JOB_ID}", "title": "Backend Engineer"}], total=3)
    assert model_facing(read) == {
        "items": [{"ref": f"job:{JOB_ID}", "title": "Backend Engineer"}],
        "total": 3,
        "truncated": False,
    }


def test_FR022_labels_use_non_private_fields_only() -> None:
    assert label_contact("Acme") == "a contact at Acme"
    assert label_round("Backend Engineer", "Zoho") == (
        "an interview round for Backend Engineer at Zoho"
    )


def test_R5_refs_round_trip_and_reject_bad_text() -> None:
    ref = Ref.parse(f"job:{JOB_ID}")
    assert (ref.kind, ref.id) == ("job", JOB_ID)
    assert str(ref) == f"job:{JOB_ID}"
    for bad in ("job", f"spaceship:{JOB_ID}", "job:not-a-uuid", f"Job:{JOB_ID}"):
        with pytest.raises(ValueError):
            Ref.parse(bad)
    assert Ref.parse(f"job:{JOB_ID}", expect="job").id == JOB_ID
    with pytest.raises(ValueError):
        Ref.parse(f"job:{JOB_ID}", expect="company")


def test_FR016_excluded_names_cannot_register() -> None:
    catalogue = Catalogue()
    catalogue.register(_spec("read", name="search_jobs"))
    with pytest.raises(ValueError):
        catalogue.register(_spec("read", name="search_jobs"))  # one definition per action
    for name in ("delete_all_data", "set_ai_key", "connect_gmail", "confirm_profile_review"):
        with pytest.raises(ExcludedActionError):
            catalogue.register(_spec("risky", name=name, targets=_targets))
    assert [t.name for t in catalogue.tool_specs()] == ["search_jobs"]
    assert catalogue.get("search_jobs") is not None
    assert catalogue.get("delete_all_data") is None


def test_FR016_every_excluded_endpoint_names_its_page() -> None:
    assert "POST /data/delete-all" in EXCLUDED
    assert "PUT /settings/ai-key" in EXCLUDED
    assert "POST /mail/connect" in EXCLUDED
    assert "POST /profile/reviews/{review_id}/confirm" in EXCLUDED
    for endpoint, excluded in EXCLUDED.items():
        assert excluded.page.startswith("/"), endpoint
        assert excluded.why, endpoint


def test_T039_tool_schemas_carry_no_noise() -> None:
    """Titles, null defaults and optional-null wrappers cost tokens on every model call."""
    import json

    from hiretitan.actions.registry import build_catalogue

    tools = build_catalogue().tool_specs()
    text = json.dumps([t.parameters for t in tools])

    assert '"title": "' not in text.replace('"title": {', "")  # a title string, not a field
    assert '"default": null' not in text
    assert '{"type": "null"}' not in text
    assert len(text) + sum(len(t.description) for t in tools) < 21_000
    assert tools[0].parameters["type"] == "object"
