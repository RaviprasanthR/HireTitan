"""LangGraph Postgres checkpointer in schema ``lg`` (set up at worker start)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

CHECKPOINT_SCHEMA: Final = "lg"


def psycopg_conninfo(database_url: str) -> str:
    """Turn a SQLAlchemy URL (``postgresql+psycopg://``) into a libpq one."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def open_checkpointer(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    """Open a pool whose connections use ``lg`` as their schema and create its tables."""
    conninfo = psycopg_conninfo(database_url)
    async with await AsyncConnection.connect(conninfo, autocommit=True) as admin:
        await admin.execute(f"CREATE SCHEMA IF NOT EXISTS {CHECKPOINT_SCHEMA}")
    pool = AsyncConnectionPool(
        conninfo,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={CHECKPOINT_SCHEMA}",
        },
        open=False,
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        yield saver
    finally:
        await pool.close()
