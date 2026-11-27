"""002m T004: Mikasa's tables (migration 0026) and repositories (data-model.md).

Real Postgres. Each rule in data-model.md is checked once in the database, so a repository bug
cannot store what the model forbids.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.assistant.infra.models import (
    CardRow,
    ChangeRow,
    ConversationRow,
    MessageRow,
)
from hiretitan.assistant.infra.repos import (
    CardsRepo,
    ChangesRepo,
    ConversationsRepo,
    MessagesRepo,
    NewChange,
)
from hiretitan.setup_wiring import SqlDeleteAllStore

TABLES = {
    "assistant_conversations",
    "assistant_messages",
    "assistant_cards",
    "assistant_changes",
}
NOW = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
ITEM = {"action": "delete_job", "args": {"job": "job:00000000-0000-0000-0000-000000000001"}}


def test_002m_0029_staged_posting_up_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0028")
    engine = create_engine(fresh_database_url)
    try:

        def states() -> str:
            found = inspect(engine).get_check_constraints("jobs", schema="app")
            return next(c["sqltext"] for c in found if c["name"].endswith("state_values"))

        assert "assistant_staged" not in inspect(engine).get_table_names(schema="app")
        assert "staged" not in states()
        command.upgrade(cfg, "0029")
        assert "assistant_staged" in inspect(engine).get_table_names(schema="app")
        assert "staged" in states()
        command.downgrade(cfg, "0028")
        assert "assistant_staged" not in inspect(engine).get_table_names(schema="app")
        assert "staged" not in states()
    finally:
        engine.dispose()


def test_002m_0028_email_draft_kind_up_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0027")
    engine = create_engine(fresh_database_url)
    try:

        def kinds_rule() -> str:
            found = inspect(engine).get_check_constraints("outreach_drafts", schema="app")
            return next(
                c["sqltext"]
                for c in found
                if c["name"].endswith("kind_values") and "recipient" not in c["name"]
            )

        assert "email" not in kinds_rule()
        command.upgrade(cfg, "0028")
        assert "email" in kinds_rule()
        command.downgrade(cfg, "0027")
        assert "email" not in kinds_rule()
    finally:
        engine.dispose()


def test_FR014_0027_summary_column_up_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0026")
    engine = create_engine(fresh_database_url)
    try:

        def columns() -> set[str]:
            found = inspect(engine).get_columns("assistant_changes", schema="app")
            return {c["name"] for c in found}

        assert "summary" not in columns()
        command.upgrade(cfg, "0027")
        assert "summary" in columns()
        command.downgrade(cfg, "0026")
        assert "summary" not in columns()
    finally:
        engine.dispose()


def test_FR026_0026_migration_up_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0025")
    engine = create_engine(fresh_database_url)
    try:
        assert not TABLES & set(inspect(engine).get_table_names(schema="app"))
        command.upgrade(cfg, "0026")
        assert set(inspect(engine).get_table_names(schema="app")) >= TABLES
        command.downgrade(cfg, "0025")
        assert not TABLES & set(inspect(engine).get_table_names(schema="app"))
    finally:
        engine.dispose()


async def _conversation(session: AsyncSession) -> ConversationRow:
    return await ConversationsRepo(session).create(now=NOW)


async def test_FR026_messages_kept_in_order(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        conv = await _conversation(session)
        repo = MessagesRepo(session)
        first = await repo.append(conv.id, author="person", text="What did I apply to?", now=NOW)
        second = await repo.append(
            conv.id, author="mikasa", text="Two jobs.", now=NOW, refs=["job:abc"]
        )
        third = await repo.append(conv.id, author="person", text="Thanks", now=NOW)
        await session.commit()

        assert [first.seq, second.seq, third.seq] == [1, 2, 3]
        listed = await repo.list_for(conv.id)
        assert [m.text for m in listed] == ["What did I apply to?", "Two jobs.", "Thanks"]
        assert listed[1].refs == ["job:abc"]
        assert listed[1].status == "complete"
        assert [m.seq for m in await repo.last(conv.id, 2)] == [2, 3]  # oldest first


async def test_FR026_title_from_first_person_message(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        conv = await _conversation(session)
        await MessagesRepo(session).append(conv.id, author="person", text="x" * 120, now=NOW)
        await session.commit()
        stored = await ConversationsRepo(session).get(conv.id)
        assert stored is not None
        assert stored.title == "x" * 80


async def test_DB_0026_checks_reject_bad_values(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    bad_rows = [
        ("author", "robot", "hi"),
        ("status", "lost", "hi"),
        ("person_text", "person", "x" * 2001),
        ("mikasa_text", "mikasa", "x" * 4001),
    ]
    for case, author_or_status, body in bad_rows:
        async with sessions() as session:
            conv = await _conversation(session)
            await session.commit()
            row = MessageRow(
                conversation_id=conv.id,
                seq=1,
                author=author_or_status
                if case in ("author", "person_text", "mikasa_text")
                else "person",
                text=body,
                status=author_or_status if case == "status" else "complete",
            )
            session.add(row)
            with pytest.raises(IntegrityError):
                await session.commit()

    async with sessions() as session:
        conv = await _conversation(session)
        message = await MessagesRepo(session).append(conv.id, author="mikasa", text="ok", now=NOW)
        await session.commit()
        conv_id, message_id = conv.id, message.id  # a rollback expires the loaded rows
        for items, state in (([], "proposed"), ([ITEM] * 26, "proposed"), ([ITEM], "maybe")):
            session.add(
                CardRow(
                    conversation_id=conv_id,
                    message_id=message_id,
                    state=state,
                    items=items,
                    fingerprints={},
                    summary="Delete a job",
                    expires_at=NOW,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()

        session.add(
            ChangeRow(
                conversation_id=conv_id,
                action="mark_applied",
                target_kind="job",
                target_id=uuid4(),
                before={},
                after={},
            )
        )  # neither a message nor a card
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_EC01_claim_turn_once(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        conv = await _conversation(session)
        await session.commit()
        repo = ConversationsRepo(session)
        assert await repo.claim_turn(conv.id, now=NOW) is True
        await session.commit()
        assert await repo.claim_turn(conv.id, now=NOW + timedelta(seconds=5)) is False
        await repo.release_turn(conv.id)
        await session.commit()
        assert await repo.claim_turn(conv.id, now=NOW + timedelta(seconds=6)) is True


async def test_EC01_stale_running_turn_freed_after_120s(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        conv = await _conversation(session)
        await session.commit()
        repo = ConversationsRepo(session)
        assert await repo.claim_turn(conv.id, now=NOW) is True
        await session.commit()
        assert await repo.claim_turn(conv.id, now=NOW + timedelta(seconds=120)) is False
        assert await repo.claim_turn(conv.id, now=NOW + timedelta(seconds=121)) is True


async def test_EC03_claim_for_apply_once(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        conv = await _conversation(session)
        message = await MessagesRepo(session).append(conv.id, author="mikasa", text="ok", now=NOW)
        card = await CardsRepo(session).create(
            conv.id,
            message.id,
            items=[ITEM],
            fingerprints={"job:1": "a" * 64},
            summary="Delete Backend Engineer at Acme",
            now=NOW,
        )
        await session.commit()
        assert card.state == "proposed"
        assert card.expires_at == NOW + timedelta(minutes=30)

        repo = CardsRepo(session)
        claimed = await repo.claim_for_apply(card.id, now=NOW)
        await session.commit()
        assert claimed is not None
        assert claimed.state == "applying"
        assert (
            await repo.claim_for_apply(card.id, now=NOW) is None
        )  # the second click finds nothing


async def test_R6_latest_change_for_target_and_undo_mark(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    target = uuid4()
    async with sessions() as session:
        conv = await _conversation(session)
        message = await MessagesRepo(session).append(conv.id, author="mikasa", text="ok", now=NOW)
        repo = ChangesRepo(session)
        older = await repo.save(
            NewChange(
                conversation_id=conv.id,
                message_id=message.id,
                action="mark_applied",
                target_kind="job",
                target_id=target,
                before={"state": "explore"},
                after={"state": "applied"},
                undoable_until=NOW + timedelta(hours=24),
            ),
            now=NOW,
        )
        newer = await repo.save(
            NewChange(
                conversation_id=conv.id,
                message_id=message.id,
                action="unmark_applied",
                target_kind="job",
                target_id=target,
                before={"state": "applied"},
                after={"state": "explore"},
                undoable_until=NOW + timedelta(hours=24),
            ),
            now=NOW + timedelta(minutes=1),
        )
        await session.commit()

        latest = await repo.latest_for("job", target)
        assert latest is not None
        assert latest.id == newer.id
        assert older.created_rows == []
        await repo.mark_undone(newer.id, now=NOW + timedelta(minutes=2))
        await session.commit()
        undone = await repo.get(newer.id)
        assert undone is not None
        assert undone.undone_at == NOW + timedelta(minutes=2)


async def test_FR027_conversation_delete_cascades(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        conv = await _conversation(session)
        message = await MessagesRepo(session).append(conv.id, author="mikasa", text="ok", now=NOW)
        card = await CardsRepo(session).create(
            conv.id, message.id, items=[ITEM], fingerprints={}, summary="Delete", now=NOW
        )
        await ChangesRepo(session).save(
            NewChange(
                conversation_id=conv.id,
                card_id=card.id,
                action="delete_job",
                target_kind="job",
                target_id=uuid4(),
                before={},
                after={},
            ),
            now=NOW,
        )
        other = await _conversation(session)
        await session.commit()

        await ConversationsRepo(session).remove(conv.id)
        await session.commit()
        for model in (MessageRow, CardRow, ChangeRow):
            assert (await session.scalars(select(model))).all() == []
        assert [c.id for c in await ConversationsRepo(session).list_recent()] == [other.id]

        await ConversationsRepo(session).clear()
        await session.commit()
        assert await ConversationsRepo(session).list_recent() == []


async def test_SC009_delete_all_truncates_assistant_tables(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        conv = await _conversation(session)
        await MessagesRepo(session).append(conv.id, author="person", text="hi", now=NOW)
        await session.commit()
    async with sessions() as session:
        await SqlDeleteAllStore(session).wipe_and_reseed()
        await session.commit()
    async with sessions() as session:
        for table in TABLES:
            count = (await session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar_one()
            assert count == 0, table
