"""Repositories for the mail tables. Method names avoid ``post``, ``put`` and ``delete`` as call
names where the no-send scanner bans them in scanned packages; deletes use ``remove``/``clear``."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.mail.domain.senders import SeedSender, normalize_address
from hiretitan.mail.infra.models import (
    MailCheckRow,
    MailConnectionRow,
    MailReadMessageRow,
    MailSenderRow,
)

PURPOSE = "job_alert"


class SenderExistsError(ValueError):
    """That address is already on the list."""


class BuiltInSenderError(ValueError):
    """A built-in sender can be switched off, not removed."""


class ConnectionRepo:
    """The one mailbox link. No row means not connected."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> MailConnectionRow | None:
        return await self._session.scalar(select(MailConnectionRow))

    async def get_for_share(self) -> MailConnectionRow | None:
        """The link, locked until the transaction ends: a Disconnect or Delete all removing it
        waits for a batch being stored, and a batch after it finds no link."""
        return await self._session.scalar(select(MailConnectionRow).with_for_update(read=True))

    async def connect(self, address: str, now: datetime) -> MailConnectionRow:
        """Create the link, or update it (a reconnect): connected, the error cleared."""
        values: dict[str, Any] = {
            "address": address,
            "state": "connected",
            "connected_at": now,
            "last_error": None,
        }
        # One statement, so a double click cannot hit the unique provider twice.
        await self._session.execute(
            pg_insert(MailConnectionRow)
            .values(provider="gmail", **values)
            .on_conflict_do_update(index_elements=[MailConnectionRow.provider], set_=values)
        )
        row = await self.get()
        assert row is not None
        await self._session.refresh(row)
        return row

    async def set_state(self, state: str, error: str | None = None) -> None:
        await self._session.execute(update(MailConnectionRow).values(state=state, last_error=error))

    async def mark_check_started(self, now: datetime) -> None:
        await self._session.execute(update(MailConnectionRow).values(last_check_started_at=now))

    async def remove(self) -> None:
        await self._session.execute(delete(MailConnectionRow))


class SendersRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[MailSenderRow]:
        rows = await self._session.scalars(
            select(MailSenderRow).order_by(
                MailSenderRow.built_in.desc(), MailSenderRow.site, MailSenderRow.address
            )
        )
        return list(rows)

    async def merge_seed(self, seed: Sequence[SeedSender]) -> int:
        """Add the shipped addresses that are missing; an existing row, and its switch, is kept."""
        if not seed:
            return 0
        # DO NOTHING on a clash: the API and the worker may both start at once.
        result = await self._session.execute(
            pg_insert(MailSenderRow)
            .values(
                [
                    {
                        "address": s.address,
                        "site": s.site,
                        "purpose": PURPOSE,
                        "built_in": True,
                        "enabled": True,
                    }
                    for s in seed
                ]
            )
            .on_conflict_do_nothing(index_elements=[MailSenderRow.address])
            .returning(MailSenderRow.id)
        )
        return len(result.all())

    async def enabled_addresses(self, purpose: str = PURPOSE) -> list[str]:
        rows = await self._session.scalars(
            select(MailSenderRow.address)
            .where(MailSenderRow.enabled.is_(True), MailSenderRow.purpose == purpose)
            .order_by(MailSenderRow.address)
        )
        return list(rows)

    async def add_custom(self, address: str) -> MailSenderRow:
        clean = normalize_address(address)
        # One statement: a double click is a clash answered here, never a 500.
        row = await self._session.scalar(
            pg_insert(MailSenderRow)
            .values(address=clean, site="other", purpose=PURPOSE, built_in=False, enabled=True)
            .on_conflict_do_nothing(index_elements=[MailSenderRow.address])
            .returning(MailSenderRow)
        )
        if row is None:
            raise SenderExistsError(f"{clean} is already on the list.")
        return cast(MailSenderRow, row)

    async def get(self, sender_id: UUID) -> MailSenderRow | None:
        return await self._session.get(MailSenderRow, sender_id)

    async def set_enabled(self, sender_id: UUID, enabled: bool) -> None:
        await self._session.execute(
            update(MailSenderRow).where(MailSenderRow.id == sender_id).values(enabled=enabled)
        )

    async def remove(self, sender_id: UUID) -> None:
        row = await self.get(sender_id)
        if row is None:
            return
        if row.built_in:
            raise BuiltInSenderError("A built-in sender can be switched off, not removed.")
        await self._session.execute(delete(MailSenderRow).where(MailSenderRow.id == sender_id))


class ReadMessagesRepo:
    """Which emails were read, so none is read twice (FR-011). Never the email itself."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def already_read(self, message_ids: Sequence[str]) -> set[str]:
        """The ids that are final. One waiting for the AI (``needs_ai``) is read again."""
        if not message_ids:
            return set()
        rows = await self._session.scalars(
            select(MailReadMessageRow.provider_message_id).where(
                MailReadMessageRow.provider_message_id.in_(message_ids),
                MailReadMessageRow.outcome != "needs_ai",
            )
        )
        return set(rows)

    async def forget_since(self, when: datetime) -> None:
        """Forget the emails received since ``when`` (FR-013e). Their sightings keep their jobs;
        the link to the email record goes empty, as on Disconnect."""
        await self._session.execute(
            delete(MailReadMessageRow).where(MailReadMessageRow.received_at >= when)
        )

    async def record(
        self,
        message_id: str,
        sender: str,
        received_at: datetime,
        outcome: str,
        reader: str | None,
        jobs_found: int,
        injection_signals: list[Any],
        mail_check_id: UUID | None,
        read_at: datetime,
    ) -> UUID:
        """Note that a message was read; a message seen before (waiting for the AI) is updated.
        Returns the record's id (the one that stays when a final answer was already there)."""
        values: dict[str, Any] = {
            "sender": sender,
            "received_at": received_at,
            "purpose": PURPOSE,
            "outcome": outcome,
            "reader": reader,
            "jobs_found": jobs_found,
            "injection_signals": injection_signals,
            "mail_check_id": mail_check_id,
            "read_at": read_at,
        }
        statement = pg_insert(MailReadMessageRow).values(provider_message_id=message_id, **values)
        # Only a message still waiting for the AI is overwritten: a slower check that also saw it
        # as ``needs_ai`` must not undo a final answer.
        row_id = await self._session.scalar(
            statement.on_conflict_do_update(
                index_elements=[MailReadMessageRow.provider_message_id],
                set_=values,
                where=MailReadMessageRow.outcome == "needs_ai",
            ).returning(MailReadMessageRow.id)
        )
        if row_id is None:  # a final answer was already there: keep it, say which record it is
            row_id = await self._session.scalar(
                select(MailReadMessageRow.id).where(
                    MailReadMessageRow.provider_message_id == message_id
                )
            )
        assert row_id is not None
        return cast(UUID, row_id)

    async def count(self) -> int:
        return int(await self._session.scalar(select(func.count(MailReadMessageRow.id))) or 0)

    async def clear(self) -> None:
        await self._session.execute(delete(MailReadMessageRow))


class MailChecksRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, search_run_id: UUID, trigger: str, window_start: datetime
    ) -> MailCheckRow:
        row = MailCheckRow(search_run_id=search_run_id, trigger=trigger, window_start=window_start)
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest(self) -> MailCheckRow | None:
        return await self._session.scalar(
            select(MailCheckRow).order_by(MailCheckRow.created_at.desc()).limit(1)
        )

    async def get_for_run(self, search_run_id: UUID) -> MailCheckRow | None:
        return await self._session.scalar(
            select(MailCheckRow).where(MailCheckRow.search_run_id == search_run_id)
        )

    async def get(self, check_id: UUID) -> MailCheckRow | None:
        return await self._session.get(MailCheckRow, check_id)

    async def mark_failed(self, check_id: UUID) -> None:
        """End a check the runner gave up on (its totals so far stay as they were)."""
        await self._session.execute(
            update(MailCheckRow).where(MailCheckRow.id == check_id).values(ended="failed")
        )

    async def set_counts(
        self,
        check_id: UUID,
        *,
        listed: int,
        skipped: int,
        read: int,
        unreadable: int,
        more_remaining: bool,
    ) -> None:
        """The running totals, written after every batch so the page can show progress."""
        await self._session.execute(
            update(MailCheckRow)
            .where(MailCheckRow.id == check_id)
            .values(
                emails_listed=listed,
                emails_skipped=skipped,
                emails_read=read,
                emails_unreadable=unreadable,
                more_remaining=more_remaining,
            )
        )

    async def finish(
        self,
        check_id: UUID,
        *,
        listed: int,
        skipped: int,
        read: int,
        unreadable: int,
        more_remaining: bool,
        ended: str,
    ) -> None:
        await self._session.execute(
            update(MailCheckRow)
            .where(MailCheckRow.id == check_id)
            .values(
                emails_listed=listed,
                emails_skipped=skipped,
                emails_read=read,
                emails_unreadable=unreadable,
                more_remaining=more_remaining,
                ended=ended,
            )
        )

    async def clear(self) -> None:
        await self._session.execute(delete(MailCheckRow))
