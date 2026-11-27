"""Undo of a change Mikasa made (002m FR-014, EC-16, research R6).

The rules live in ``assistant.domain.kinds.undo_refusal``; this runs them inside one transaction
with the action's own undo, so a refused Undo changes nothing and an allowed one applies once.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from hiretitan.assistant.application.ports import ChangeRecord, UndoUnitFactory
from hiretitan.assistant.domain.kinds import UndoRefusal, undo_refusal

MESSAGES: dict[str, str] = {
    "already_undone": "That change was already undone.",
    "not_undoable": "That change can't be undone here.",
    "too_late": "That change is more than a day old, so it can't be undone here.",
    "not_latest": "Something else changed this item after that, so undo the newer change first.",
    "changed_since": "This item changed after that, so undoing would overwrite the newer change.",
}


class ChangeNotFoundError(LookupError):
    pass


class UndoRefusedError(Exception):
    def __init__(self, reason: UndoRefusal) -> None:
        super().__init__(MESSAGES[reason])
        self.reason: str = reason


async def undo_change(open_unit: UndoUnitFactory, change_id: UUID, now: datetime) -> ChangeRecord:
    async with open_unit() as unit:
        change = await unit.change(change_id)
        if change is None:
            raise ChangeNotFoundError(str(change_id))
        refusal = undo_refusal(
            undone_at=change.undone_at,
            undoable_until=change.undoable_until,
            is_latest=await unit.is_latest(change),
            current=await unit.current(change),
            after=change.after,
            now=now,
        )
        if refusal is not None:
            raise UndoRefusedError(refusal)
        await unit.run_undo(change)
        await unit.mark_undone(change.id, now)
        await unit.commit()
        return change
