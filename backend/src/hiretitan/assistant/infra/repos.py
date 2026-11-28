"""Repositories for Mikasa's tables (002m data-model.md).

Method names avoid ``delete``/``put``/``post``: the no-send scanner bans those call names in the
packages it scans (``remove``, ``clear``, ``save`` instead).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.assistant.infra.models import (
    TITLE_MAX,
    CardRow,
    ChangeRow,
    ConversationRow,
    MessageRow,
)

STALE_TURN = timedelta(seconds=120)
CARD_LIFETIME = timedelta(minutes=30)


class ConversationsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, now: datetime) -> ConversationRow:
        row = ConversationRow(created_at=now, last_used_at=now, turn_running=False)
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, conversation_id: UUID) -> ConversationRow | None:
        return await self._session.get(ConversationRow, conversation_id, populate_existing=True)

    async def list_recent(self, limit: int = 50) -> list[ConversationRow]:
        rows = await self._session.scalars(
            select(ConversationRow).order_by(ConversationRow.last_used_at.desc()).limit(limit)
        )
        return list(rows)

    async def claim_turn(self, conversation_id: UUID, *, now: datetime) -> bool:
        """Mark a turn as running; False when one is already running (EC-01).

        A turn started more than 120 s ago is treated as ended, so a crash never leaves the
        conversation stuck.
        """
        claimed = await self._session.scalar(
            update(ConversationRow)
            .where(
                ConversationRow.id == conversation_id,
                or_(
                    ConversationRow.turn_running.is_(False),
                    ConversationRow.turn_started_at < now - STALE_TURN,
                ),
            )
            .values(turn_running=True, turn_started_at=now, last_used_at=now)
            .returning(ConversationRow.id)
        )
        return claimed is not None

    async def release_turn(self, conversation_id: UUID) -> None:
        await self._session.execute(
            update(ConversationRow)
            .where(ConversationRow.id == conversation_id)
            .values(turn_running=False, turn_started_at=None)
        )

    async def remove(self, conversation_id: UUID, *, now: datetime) -> bool:
        """Delete it unless a turn is running in it (that turn would lose its reply)."""
        gone = await self._session.scalar(
            delete(ConversationRow)
            .where(ConversationRow.id == conversation_id, _idle(now))
            .returning(ConversationRow.id)
        )
        return gone is not None

    async def clear(self, *, now: datetime) -> None:
        """Delete every conversation that has no turn running."""
        await self._session.execute(delete(ConversationRow).where(_idle(now)))


def _idle(now: datetime) -> Any:
    return or_(
        ConversationRow.turn_running.is_(False),
        ConversationRow.turn_started_at < now - STALE_TURN,
    )


class MessagesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        conversation_id: UUID,
        *,
        author: str,
        text: str,
        now: datetime,
        status: str = "complete",
        refs: Sequence[str] = (),
        tool_trace: Sequence[Any] = (),
        signals: Sequence[Any] = (),
        error: dict[str, Any] | None = None,
    ) -> MessageRow:
        """Add the next message. The conversation row is locked, so ``seq`` has no gaps or
        duplicates even when a card and a turn write at once."""
        conversation = await self._session.scalar(
            select(ConversationRow).where(ConversationRow.id == conversation_id).with_for_update()
        )
        if conversation is None:
            raise LookupError(f"No conversation {conversation_id}")
        last = await self._session.scalar(
            select(func.coalesce(func.max(MessageRow.seq), 0)).where(
                MessageRow.conversation_id == conversation_id
            )
        )
        row = MessageRow(
            conversation_id=conversation_id,
            seq=int(last or 0) + 1,
            author=author,
            text=text,
            status=status,
            refs=list(refs),
            tool_trace=list(tool_trace),
            signals=list(signals),
            error=error,
            created_at=now,
        )
        self._session.add(row)
        conversation.last_used_at = now
        if author == "person" and conversation.title is None:
            conversation.title = " ".join(text.split())[:TITLE_MAX] or None
        await self._session.flush()
        return row

    async def get(self, message_id: UUID) -> MessageRow | None:
        return await self._session.get(MessageRow, message_id)

    async def list_for(self, conversation_id: UUID) -> list[MessageRow]:
        rows = await self._session.scalars(
            select(MessageRow)
            .where(MessageRow.conversation_id == conversation_id)
            .order_by(MessageRow.seq)
        )
        return list(rows)

    async def last(self, conversation_id: UUID, count: int) -> list[MessageRow]:
        """The newest ``count`` messages, oldest first (the model's window, research R10)."""
        rows = await self._session.scalars(
            select(MessageRow)
            .where(MessageRow.conversation_id == conversation_id)
            .order_by(MessageRow.seq.desc())
            .limit(count)
        )
        return list(reversed(list(rows)))


class CardsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        conversation_id: UUID,
        message_id: UUID,
        *,
        items: Sequence[dict[str, Any]],
        fingerprints: dict[str, str],
        summary: str,
        now: datetime,
    ) -> CardRow:
        row = CardRow(
            conversation_id=conversation_id,
            message_id=message_id,
            state="proposed",
            items=list(items),
            fingerprints=dict(fingerprints),
            summary=summary,
            expires_at=now + CARD_LIFETIME,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, card_id: UUID) -> CardRow | None:
        return await self._session.get(CardRow, card_id, populate_existing=True)

    async def list_for(self, conversation_id: UUID) -> list[CardRow]:
        rows = await self._session.scalars(
            select(CardRow)
            .where(CardRow.conversation_id == conversation_id)
            .order_by(CardRow.created_at)
        )
        return list(rows)

    async def claim_for_apply(self, card_id: UUID, *, now: datetime) -> CardRow | None:
        """``proposed`` → ``applying`` in one statement; a second confirm finds nothing (EC-03)."""
        claimed = await self._session.scalar(
            update(CardRow)
            .where(CardRow.id == card_id, CardRow.state == "proposed")
            .values(state="applying", decided_at=now)
            .returning(CardRow.id)
        )
        if claimed is None:
            return None
        return await self.get(card_id)

    async def set_state(
        self,
        card_id: UUID,
        state: str,
        *,
        now: datetime,
        result: list[Any] | None = None,
    ) -> None:
        values: dict[str, Any] = {"state": state, "decided_at": now}
        if result is not None:
            values["result"] = result
        await self._session.execute(update(CardRow).where(CardRow.id == card_id).values(**values))


@dataclass(frozen=True, slots=True)
class NewChange:
    conversation_id: UUID
    action: str
    target_kind: str
    target_id: UUID
    before: dict[str, Any]
    after: dict[str, Any]
    message_id: UUID | None = None
    card_id: UUID | None = None
    created_rows: list[str] = field(default_factory=list)
    undoable_until: datetime | None = None
    summary: str | None = None


class ChangesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, change: NewChange, *, now: datetime) -> ChangeRow:
        row = ChangeRow(
            conversation_id=change.conversation_id,
            message_id=change.message_id,
            card_id=change.card_id,
            action=change.action,
            summary=change.summary[:2000] if change.summary else None,
            target_kind=change.target_kind,
            target_id=change.target_id,
            before=change.before,
            after=change.after,
            created_rows=list(change.created_rows),
            undoable_until=change.undoable_until,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, change_id: UUID) -> ChangeRow | None:
        return await self._session.get(ChangeRow, change_id, populate_existing=True)

    async def get_for_update(self, change_id: UUID) -> ChangeRow | None:
        """The change, locked until the transaction ends: two Undo presses apply once (EC-03)."""
        return await self._session.scalar(
            select(ChangeRow).where(ChangeRow.id == change_id).with_for_update()
        )

    async def latest_for(self, target_kind: str, target_id: UUID) -> ChangeRow | None:
        return await self._session.scalar(
            select(ChangeRow)
            .where(
                ChangeRow.target_kind == target_kind,
                ChangeRow.target_id == target_id,
                ChangeRow.undone_at.is_(None),  # an undone change no longer counts as the latest
            )
            .order_by(ChangeRow.created_at.desc(), ChangeRow.id.desc())
            .limit(1)
        )

    async def list_for(self, conversation_id: UUID) -> list[ChangeRow]:
        rows = await self._session.scalars(
            select(ChangeRow)
            .where(ChangeRow.conversation_id == conversation_id)
            .order_by(ChangeRow.created_at)
        )
        return list(rows)

    async def mark_undone(self, change_id: UUID, *, now: datetime) -> None:
        await self._session.execute(
            update(ChangeRow).where(ChangeRow.id == change_id).values(undone_at=now)
        )
