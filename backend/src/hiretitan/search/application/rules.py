"""Propose, edit, approve and check search rules (US2, FR-001 to FR-006).

The person owns the rules: a proposal never changes the approved set, and only one set is
approved at a time. Reading the profile and preferences goes through ``ProposalSource`` so this
module never reaches into those features.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from hiretitan.search.application.ports import ProposalSource, RuleSetStore, StoredRuleSet
from hiretitan.search.domain.proposer import propose_rules
from hiretitan.search.domain.rules import SearchRules
from hiretitan.search.domain.rules_serialization import rules_from_dict, rules_to_dict

UnavailableReason = Literal["no_confirmed_profile", "no_preferences"]


class RulesUnavailableError(Exception):
    """A proposal cannot be made yet: the profile or the preferences are missing."""

    def __init__(self, reason: UnavailableReason) -> None:
        super().__init__(reason)
        self.reason = reason


class NoProposalError(Exception):
    """There is no open proposal to edit, approve or discard."""


class RulesNotApprovedError(Exception):
    """A search needs approved rules (US2 AS5)."""


@dataclass(frozen=True, slots=True)
class RuleSetView:
    id: UUID
    version: int
    status: str
    rules: SearchRules
    approved_at: datetime | None


def _view(row: StoredRuleSet) -> RuleSetView:
    return RuleSetView(row.id, row.version, row.status, rules_from_dict(row.rules), row.approved_at)


def _basis(profile_version_id: UUID, preferences_saved_at: datetime) -> dict[str, Any]:
    return {
        "profile_version_id": str(profile_version_id),
        "preferences_saved_at": preferences_saved_at.isoformat(),
    }


class RulesService:
    def __init__(
        self,
        store: RuleSetStore,
        source: ProposalSource,
        synonyms: dict[str, tuple[str, ...]],
    ) -> None:
        self._store = store
        self._source = source
        self._synonyms = synonyms

    async def current(self) -> tuple[RuleSetView | None, RuleSetView | None]:
        """``(approved, proposed)``; either may be missing."""
        approved = await self._store.approved()
        proposed = await self._store.proposed()
        return (
            _view(approved) if approved is not None else None,
            _view(proposed) if proposed is not None else None,
        )

    async def propose(self) -> RuleSetView:
        """Build a fresh proposal from the profile and preferences. The approved set stays."""
        facts = await self._source.read()
        rules = propose_rules(facts.source, self._synonyms)
        row = await self._store.propose(
            rules_to_dict(rules), _basis(facts.profile_version_id, facts.preferences_saved_at)
        )
        return _view(row)

    async def edit_proposal(self, rules: SearchRules) -> RuleSetView:
        rules.validate()
        row = await self._store.update_proposed(rules_to_dict(rules))
        if row is None:
            raise NoProposalError
        return _view(row)

    async def approve(self) -> RuleSetView:
        """Validate and approve the open proposal; the old approved set becomes superseded."""
        proposed = await self._store.proposed()
        if proposed is None:
            raise NoProposalError
        rules_from_dict(proposed.rules).validate()
        return _view(await self._store.approve(proposed.id))

    async def discard_proposal(self) -> None:
        await self._store.discard_proposed()

    async def require_approved(self) -> RuleSetView:
        approved = await self._store.approved()
        if approved is None:
            raise RulesNotApprovedError
        return _view(approved)

    async def is_stale(self) -> bool:
        """True when the profile or preferences changed since the approved set was built."""
        approved = await self._store.approved()
        if approved is None:
            return False
        try:
            facts = await self._source.read()
        except RulesUnavailableError:
            return False
        return approved.based_on != _basis(facts.profile_version_id, facts.preferences_saved_at)
