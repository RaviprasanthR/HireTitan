"""``MailStore`` over the mail tables: one transaction per call."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.ports import ConnectionRecord
from hiretitan.mail.infra.repos import ConnectionRepo, MailChecksRepo, ReadMessagesRepo


class SqlMailStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def connection(self) -> ConnectionRecord | None:
        async with self._sessions() as session:
            row = await ConnectionRepo(session).get()
            if row is None:
                return None
            return ConnectionRecord(
                row.state, row.address, row.last_check_started_at, row.last_error
            )

    async def connect(self, address: str, now: datetime) -> None:
        async with self._sessions() as session:
            await ConnectionRepo(session).connect(address, now)
            await session.commit()

    async def set_state(self, state: str, error: str | None) -> None:
        async with self._sessions() as session:
            await ConnectionRepo(session).set_state(state, error)
            await session.commit()

    async def erase_all(self) -> None:
        async with self._sessions() as session:
            # read-email records first: the checks they point at are removed next
            await ReadMessagesRepo(session).clear()
            await MailChecksRepo(session).clear()
            await ConnectionRepo(session).remove()
            await session.commit()
