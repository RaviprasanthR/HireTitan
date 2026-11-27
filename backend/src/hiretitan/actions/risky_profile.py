"""Mikasa's risky changes to preferences, search rules and the display name (002m
contracts/actions.md). Each waits on a confirm card. Rule changes go through the same proposal
and approval as the Search rules page (constitution I). No action writes profile facts (FR-018).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, Applied
from hiretitan.actions.text import screened
from hiretitan.preferences.api.router import PreferencesModel
from hiretitan.preferences.application.service import (
    PreferencesInvalid,
    get_preferences,
    save_preferences,
)
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.search.api.rules import SearchRulesModel
from hiretitan.search.application.rules import NoProposalError, RulesNotApprovedError
from hiretitan.search.domain.rules import RulesInvalidError
from hiretitan.search.infra.repos import RuleSetsRepo
from hiretitan.setup.application.onboarding import set_display_name
from hiretitan.setup.infra.settings_repo import SettingsRepo

Targets = Mapping[str, Mapping[str, Any]]
_ZERO = UUID(int=0)  # preferences, rules and the name are single rows with no id of their own


class _At:
    """A clock that answers with the action's time."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _merged(current: dict[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, value in changes.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _merged(merged[key], value)
        else:
            merged[key] = value
    return merged


# ---- preferences ---------------------------------------------------------------------------


class PreferencesArgs(BaseModel):
    changes: dict[str, Any] = Field(
        description="Only the preference fields to change, named as get_preferences shows them"
    )


async def _preferences_target(ctx: ActionContext, args: PreferencesArgs) -> Targets:
    stored = await get_preferences(PreferencesRepo(ctx.session))
    current = PreferencesModel.from_domain(stored.content).model_dump(mode="json")
    return {
        "preferences": {
            "label": "your preferences: " + ", ".join(sorted(args.changes)),
            "now": current,
        }
    }


async def update_preferences(ctx: ActionContext, args: PreferencesArgs) -> Applied | ActionError:
    repo = PreferencesRepo(ctx.session)
    stored = await get_preferences(repo)
    before = PreferencesModel.from_domain(stored.content).model_dump(mode="json")
    try:
        model = PreferencesModel.model_validate(_merged(before, args.changes))
        await save_preferences(repo, _At(ctx.now), model.to_domain())
    except ValidationError as error:
        return ActionError(
            "invalid", f"Some fields are not valid: {error.error_count()} problem(s)."
        )
    except PreferencesInvalid as invalid:
        return ActionError("invalid", "; ".join(e.message for e in invalid.errors))
    after = model.model_dump(mode="json")
    shown, _ = screened(sorted(args.changes))
    return Applied(
        "preferences",
        _ZERO,
        before,
        after,
        f"Saved your preferences ({', '.join(shown)}).",
    )


# ---- search rules --------------------------------------------------------------------------


class RulesArgs(BaseModel):
    changes: dict[str, Any] = Field(
        description="Only the rule fields to change, named as get_search_rules shows them"
    )


class NoArgs(BaseModel):
    pass


async def _rules_target(ctx: ActionContext, args: Any) -> Targets:
    repo = RuleSetsRepo(ctx.session)
    approved, proposal = await repo.approved(), await repo.proposed()
    return {
        "rules": {
            "label": "your search rules",
            "approved": approved.version if approved else None,
            "proposal": proposal.version if proposal else None,
            "proposal_rules": proposal.rules if proposal else None,
        }
    }


def _service(ctx: ActionContext) -> Any:
    factory = ctx.services.rules_service
    if factory is None:
        raise LookupError("Search rules can't be changed from here.")
    return factory(ctx.session)


async def edit_rule_proposal(ctx: ActionContext, args: RulesArgs) -> Applied | ActionError:
    """A proposal the person approves next (here or on the Search rules page), never a direct
    change to the rules searches use."""
    try:
        service = _service(ctx)
        _, proposal = await service.current()
        if proposal is None:
            proposal = await service.propose_from_approved()
        current = SearchRulesModel.from_domain(proposal.rules).model_dump(mode="json")
        edited = SearchRulesModel.model_validate(_merged(current, args.changes))
        await service.edit_proposal(edited.to_domain())
    except LookupError as error:
        return ActionError("unavailable", str(error))
    except RulesNotApprovedError:
        return ActionError("rules_not_approved", "There are no approved rules to edit.")
    except (ValidationError, RulesInvalidError) as error:
        return ActionError("invalid", f"Those rules are not valid: {error}")
    return Applied(
        "rules",
        _ZERO,
        current,
        edited.model_dump(mode="json"),
        "Changed the proposed search rules. Approve them to use them.",
    )


async def approve_rule_proposal(ctx: ActionContext, args: NoArgs) -> Applied | ActionError:
    try:
        view = await _service(ctx).approve()
    except LookupError as error:
        return ActionError("unavailable", str(error))
    except NoProposalError:
        return ActionError("no_proposal", "There is no proposal to approve.")
    except RulesInvalidError as error:
        return ActionError("invalid", str(error))
    return Applied("rules", _ZERO, {}, {"version": view.version}, "Approved the search rules.")


async def discard_rule_proposal(ctx: ActionContext, args: NoArgs) -> Applied | ActionError:
    try:
        await _service(ctx).discard_proposal()
    except LookupError as error:
        return ActionError("unavailable", str(error))
    return Applied("rules", _ZERO, {}, {}, "Discarded the proposed search rules.")


# ---- display name --------------------------------------------------------------------------


class NameArgs(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


async def _name_target(ctx: ActionContext, args: NameArgs) -> Targets:
    return {"name": {"label": "the name HireTitan greets you with"}}


async def set_name(ctx: ActionContext, args: NameArgs) -> Applied | ActionError:
    try:
        await set_display_name(SettingsRepo(ctx.session), args.display_name)
    except ValueError as invalid:
        return ActionError("invalid", str(invalid))
    return Applied("settings", _ZERO, {}, {}, "Changed the name HireTitan greets you with.")


def _risky(
    name: str,
    description: str,
    args: type[BaseModel],
    handler: Any,
    targets: Any,
    title: str,
    mirrors: tuple[str, ...],
    invalidate: tuple[str, ...],
) -> ActionSpec:
    return ActionSpec(
        name=name,
        description=description,
        args=args,
        kind="risky",
        handler=handler,
        targets=targets,
        card_title=title,
        invalidate=invalidate,
        mirrors=mirrors,
    )


CHANGES: tuple[ActionSpec, ...] = (
    _risky(
        "update_preferences",
        "Change some of the person's job preferences.",
        PreferencesArgs,
        update_preferences,
        _preferences_target,
        "Change",
        ("PUT /preferences",),
        ("preferences",),
    ),
    _risky(
        "edit_rule_proposal",
        "Propose changed search rules; the person approves them after.",
        RulesArgs,
        edit_rule_proposal,
        _rules_target,
        "Propose changes to",
        ("POST /search/rules/proposal/from-approved", "PUT /search/rules/proposal"),
        ("search-rules",),
    ),
    _risky(
        "approve_rule_proposal",
        "Approve the proposed search rules, so searches use them.",
        NoArgs,
        approve_rule_proposal,
        _rules_target,
        "Approve",
        ("POST /search/rules/proposal/approve",),
        ("search-rules",),
    ),
    _risky(
        "discard_rule_proposal",
        "Discard the proposed search rules.",
        NoArgs,
        discard_rule_proposal,
        _rules_target,
        "Discard the proposal for",
        ("DELETE /search/rules/proposal",),
        ("search-rules",),
    ),
    _risky(
        "set_display_name",
        "Change the name HireTitan greets the person with.",
        NameArgs,
        set_name,
        _name_target,
        "Change",
        ("PUT /onboarding/name",),
        ("onboarding",),
    ),
)
