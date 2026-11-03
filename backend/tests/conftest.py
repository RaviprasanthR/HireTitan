"""Shared test harness (T006).

* ``postgres_url``: one real ``postgres:16`` container per test session
  (Testcontainers), migrated once with ``alembic upgrade head``.
* ``db_engine`` / ``db_session``: an async engine for the session, and per test an
  ``AsyncSession`` inside an outer transaction that is rolled back afterwards.
  ``session.commit()`` in code under test only releases a savepoint.
* ``tmp_data_dir``: an empty data dir, also exported as ``HIRETITAN_DATA_DIR``.
* ``fake_clock``: a ``FakeClock`` fixed at 2026-11-04 09:00 UTC.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from hiretitan.platform.clock import FakeClock

BACKEND = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:16"


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    # psycopg's async mode can't run on Windows' default Proactor loop.
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as container:
        url = container.get_connection_url()
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture(scope="session")
async def db_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        outer = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("HIRETITAN_DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 4, 9, 0, tzinfo=UTC))
