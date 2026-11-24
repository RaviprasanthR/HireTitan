"""Confirming or cancelling a card of risky changes (002m FR-010 to FR-013, EC-02, EC-03, R7).

Nothing on a card changes until the person confirms it. Confirming applies every item in one
transaction, or none; a card whose targets changed since it was proposed expires instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from hiretitan.assistant.application.ports import ApplyOutcome, CardUnitFactory
from hiretitan.assistant.domain.fingerprints import stale_targets
from hiretitan.assistant.domain.kinds import card_is_open

REFUSALS: dict[str, tuple[int, str]] = {
    "not_found": (404, "That card does not exist."),
    "not_proposed": (409, "That card was already decided."),
    "expired": (409, "That card has expired. Ask Mikasa again."),
    "stale": (
        409,
        "Something changed since Mikasa proposed this, so it was not applied. Ask again.",
    ),
}


class CardRefusedError(Exception):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(detail or REFUSALS[reason][1])
        self.reason = reason


class CardInvalidError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class CardFailedError(Exception):
    """An item could not be applied; the whole card was rolled back."""


def edited(
    items: list[dict[str, Any]], edits: Mapping[int, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The items with the person's edits, only for arguments the card lets them change."""
    changed = []
    for index, item in enumerate(items):
        allowed = set(item.get("editable", []))
        new_args = {
            **item["args"],
            **{k: v for k, v in edits.get(index, {}).items() if k in allowed},
        }
        changed.append({**item, "args": new_args})
    return changed


async def confirm_card(
    open_unit: CardUnitFactory,
    card_id: UUID,
    edits: Mapping[int, Mapping[str, Any]],
    now: datetime,
) -> ApplyOutcome:
    async with open_unit() as unit:
        card = await unit.card(card_id)
        if card is None:
            raise CardRefusedError("not_found")
        if card.state != "proposed":
            raise CardRefusedError("not_proposed")
        if not card_is_open(card.state, card.expires_at, now):
            await unit.set_state(card_id, "expired", now)
            await unit.commit()
            raise CardRefusedError("expired")
        items = edited(card.items, edits)
        if problems := await unit.problems(items):
            raise CardInvalidError(problems)
        if stale_targets(card.fingerprints, await unit.fingerprints(card.items)):
            await unit.set_state(card_id, "expired", now)
            await unit.commit()
            raise CardRefusedError("stale")
        if not await unit.claim(card_id, now):
            raise CardRefusedError("not_proposed")
        outcome = await unit.apply(card, items, now)
        if not outcome.ok:
            await unit.rollback()
            await unit.set_state(card_id, "failed", now, [{"error": outcome.error}])
            await unit.commit()
            raise CardFailedError(outcome.error or "The change could not be made.")
        await unit.set_state(card_id, "applied", now, outcome.results)
        await unit.commit()
    for hook in outcome.after_commit:
        await hook()
    return outcome


async def cancel_card(open_unit: CardUnitFactory, card_id: UUID, now: datetime) -> None:
    async with open_unit() as unit:
        card = await unit.card(card_id)
        if card is None:
            raise CardRefusedError("not_found")
        if card.state != "proposed":
            raise CardRefusedError("not_proposed")
        if not await unit.claim(card_id, now):
            raise CardRefusedError("not_proposed")
        await unit.set_state(card_id, "cancelled", now)
        await unit.commit()
