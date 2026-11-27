"""``TurnStore`` on Postgres: each step in its own short transaction (002m research R2).

A turn streams for seconds; holding one transaction open for all of it would keep row locks
while the model writes. Every write here commits at once instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.assistant.application.ports import LlmRound, StoredMessage
from hiretitan.assistant.infra.models import ConversationRow, MessageRow
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord

TASK = "mikasa_turn"


class SqlTurnStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def conversation_exists(self, conversation_id: UUID) -> bool:
        async with self._sessions() as session:
            return await session.get(ConversationRow, conversation_id) is not None

    async def claim_turn(self, conversation_id: UUID, now: datetime) -> bool:
        async with self._sessions() as session:
            claimed = await ConversationsRepo(session).claim_turn(conversation_id, now=now)
            await session.commit()
            return claimed

    async def release_turn(self, conversation_id: UUID) -> None:
        async with self._sessions() as session:
            await ConversationsRepo(session).release_turn(conversation_id)
            await session.commit()

    async def add_person_message(
        self, conversation_id: UUID, text: str, signals: Sequence[dict[str, Any]], now: datetime
    ) -> UUID:
        async with self._sessions() as session:
            row = await MessagesRepo(session).append(
                conversation_id, author="person", text=text, now=now, signals=signals
            )
            await session.commit()
            return row.id

    async def add_mikasa_message(
        self,
        conversation_id: UUID,
        *,
        text: str,
        status: str,
        refs: Sequence[str],
        tool_trace: Sequence[dict[str, Any]],
        error: dict[str, Any] | None,
        now: datetime,
    ) -> UUID:
        async with self._sessions() as session:
            row = await MessagesRepo(session).append(
                conversation_id,
                author="mikasa",
                text=text,
                now=now,
                status=status,
                refs=refs,
                tool_trace=tool_trace,
                error=error,
            )
            await session.commit()
            return row.id

    async def recent(self, conversation_id: UUID, count: int) -> list[StoredMessage]:
        async with self._sessions() as session:
            rows = await MessagesRepo(session).last(conversation_id, count)
            return [StoredMessage(r.id, r.author, r.text, list(r.refs)) for r in rows]

    async def known_refs(self, conversation_id: UUID) -> set[str]:
        async with self._sessions() as session:
            found = await session.scalars(
                select(MessageRow.refs).where(MessageRow.conversation_id == conversation_id)
            )
            return {str(ref) for refs in found for ref in refs}

    async def last_person_text(self, conversation_id: UUID) -> str | None:
        async with self._sessions() as session:
            return await session.scalar(
                select(MessageRow.text)
                .where(MessageRow.conversation_id == conversation_id, MessageRow.author == "person")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )

    async def record_round(self, rounds: LlmRound) -> None:
        async with self._sessions() as session:
            await CallsRepo(session).record(
                LlmCallRecord(
                    task=TASK,
                    prompt_name=rounds.prompt_name,
                    prompt_version=rounds.prompt_version,
                    provider=rounds.provider,
                    model=rounds.model,
                    input_tokens=rounds.usage.input_tokens,
                    cached_input_tokens=rounds.usage.cached_input_tokens,
                    output_tokens=rounds.usage.output_tokens,
                    latency_ms=rounds.usage.latency_ms,
                    outcome=rounds.outcome,
                )
            )
            await session.commit()
