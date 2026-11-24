"""Quick actions (002m FR-029, amended 2026-11-24): a form's answers run HireTitan's own actions
through the same catalogue as a chat turn, so the same rules, changes and Undo apply, but no AI
call is made and HireTitan writes the answer itself. A draft goes to the drafts workflow, which
writes it exactly as from the job's page.

The answer names items by ref (the panel shows their cards, private details staying in the
browser), so nothing here needs the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from hiretitan.assistant.application.ports import (
    CallContext,
    CardNotice,
    ChangeNotice,
    ToolOutcome,
)
from hiretitan.assistant.application.turn import (
    ConversationNotFoundError,
    TurnDeps,
    TurnRunningError,
)
from hiretitan.assistant.domain.quick import STATUS_ACTION

MAX_SHOWN = 10


@dataclass(frozen=True, slots=True)
class QuickResult:
    message_id: UUID
    text: str
    refs: list[str] = field(default_factory=list)
    changes: list[ChangeNotice] = field(default_factory=list)
    cards: list[CardNotice] = field(default_factory=list)


def _text(empty: str, outcomes: list[ToolOutcome]) -> tuple[str, list[str]]:
    """What the actions' results say, in HireTitan's own words, and the refs to show."""
    lines: list[str] = []
    refs: list[str] = []
    for outcome in outcomes:
        payload = outcome.payload
        if "error" in payload:
            lines.append(str(payload.get("message") or payload["error"]))
            continue
        if outcome.change is not None:
            lines.append(outcome.change.summary)
        if outcome.card is not None:
            lines.append(f"{outcome.card.summary}. Confirm below to go ahead.")
        refs.extend(r for r in outcome.refs[:MAX_SHOWN] if r not in refs)
    if not lines:
        return empty, refs
    return "\n".join(line for line in lines if line), refs


async def _claim(deps: TurnDeps, conversation_id: UUID) -> None:
    if not await deps.store.conversation_exists(conversation_id):
        raise ConversationNotFoundError
    if not await deps.store.claim_turn(conversation_id, deps.now()):
        raise TurnRunningError


async def run_status(
    deps: TurnDeps, conversation_id: UUID, job_ref: str, status: str
) -> QuickResult:
    """Set a job's status from the quick form: one catalogue action, with its Undo."""
    action, words = STATUS_ACTION[status]
    await _claim(deps, conversation_id)
    now = deps.now()
    try:
        message_id = await deps.store.add_person_message(
            conversation_id, f"Update a job's status: {words}", [], now
        )
        outcome = await deps.catalog.call(
            action,
            json.dumps({"job": job_ref}),
            CallContext(conversation_id, now, message_id=message_id),
        )
        text, refs = _text("Nothing changed.", [outcome])
        await deps.store.add_mikasa_message(
            conversation_id,
            text=text,
            status="complete",
            refs=refs,
            tool_trace=[
                {"tool": action, "kind": outcome.kind, "valid": outcome.valid, "refs": refs}
            ],
            error=None,
            now=now,
        )
    finally:
        await deps.store.release_turn(conversation_id)
    changes = [outcome.change] if outcome.change is not None else []
    if deps.publish is not None:
        for change in changes:
            await deps.publish(change.invalidate)
    cards = [outcome.card] if outcome.card is not None else []
    return QuickResult(message_id=message_id, text=text, refs=refs, changes=changes, cards=cards)
