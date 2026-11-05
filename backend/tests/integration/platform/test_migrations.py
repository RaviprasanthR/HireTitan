"""T009: database access, uuid7 ids and the Alembic baseline (schema ``app``)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import String, create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hiretitan.platform.db import Base, IdTimestampMixin, uuid7
from hiretitan.platform.db.models import import_all_models


def test_upgrade_and_downgrade_baseline(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    """Every migration upgrades to head and downgrades cleanly back to base."""
    cfg = make_alembic_config(fresh_database_url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = create_engine(fresh_database_url)  # psycopg 3 serves sync and async
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert "app" in inspect(conn).get_schema_names()
            version = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
            assert version == head

        command.downgrade(cfg, "base")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT count(*) FROM app.alembic_version")).scalar()
            assert rows == 0
            assert inspect(conn).get_table_names(schema="app") == ["alembic_version"]

        command.upgrade(cfg, "head")  # and can be re-applied
    finally:
        engine.dispose()


def test_models_match_migrations(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    """The ORM tables and the migrations describe the same schema (no drift)."""
    command.upgrade(make_alembic_config(fresh_database_url), "head")
    import_all_models()
    engine = create_engine(fresh_database_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(
                conn,
                opts={
                    "include_schemas": True,
                    "include_name": lambda name, type_, _: type_ != "schema" or name == "app",
                    "compare_type": True,
                    "version_table_schema": "app",
                },
            )
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    assert diff == []


def test_uuid7_ids_are_time_ordered() -> None:
    ids = [uuid7() for _ in range(2000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert all(i.version == 7 for i in ids)
    assert all(i.variant == "specified in RFC 4122" for i in ids)


def test_uuid7_embeds_unix_milliseconds() -> None:
    before = int(datetime.now().timestamp() * 1000)  # noqa: DTZ005 - epoch ms only
    ms = uuid7().int >> 80
    after = int(datetime.now().timestamp() * 1000)  # noqa: DTZ005
    assert before <= ms <= after


class _ProbeBase(DeclarativeBase):
    pass


class _Probe(IdTimestampMixin, _ProbeBase):
    __tablename__ = "mixin_probe"
    name: Mapped[str] = mapped_column(String(20))


async def test_mixin_assigns_uuid7_and_utc_timestamps(db_session: AsyncSession) -> None:
    conn = await db_session.connection()
    await conn.run_sync(_ProbeBase.metadata.create_all)
    first, second = _Probe(name="a"), _Probe(name="b")
    db_session.add(first)
    await db_session.flush()
    db_session.add(second)
    await db_session.flush()
    await db_session.refresh(first)

    assert isinstance(first.id, UUID)
    assert first.id.version == 7
    assert first.id < second.id
    assert first.created_at.tzinfo is not None
    assert first.created_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    assert first.updated_at >= first.created_at
