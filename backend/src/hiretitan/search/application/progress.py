"""Yes/no facts about search progress, for the setup checklist (read through this module only)."""

from __future__ import annotations

from typing import Any, Protocol

from hiretitan.search.application.ports import StoredRuleSet


class ApprovedRulesReader(Protocol):
    async def approved(self) -> StoredRuleSet | None: ...


class LatestRunReader(Protocol):
    async def latest(self) -> Any | None: ...


async def rules_approved(rule_sets: ApprovedRulesReader) -> bool:
    """A proposal is not approval: only an approved set counts."""
    return await rule_sets.approved() is not None


async def searched_once(runs: LatestRunReader) -> bool:
    """At least one search has been started."""
    return await runs.latest() is not None
