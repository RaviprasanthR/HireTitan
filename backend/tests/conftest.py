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
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from hiretitan.platform.clock import FakeClock
from hiretitan.platform.db import create_engine as create_engine_for
from hiretitan.platform.db import session_factory

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
def make_alembic_config() -> Callable[[str], Config]:
    return alembic_config


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as container:
        yield container


@pytest.fixture(scope="session")
def postgres_url(postgres_container: PostgresContainer) -> str:
    """The shared test database, migrated to head once per session."""
    url = postgres_container.get_connection_url()
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture
def fresh_database_url(postgres_container: PostgresContainer) -> Iterator[str]:
    """An empty, unmigrated database for migration tests; dropped afterwards."""
    name = f"t_{uuid.uuid4().hex[:12]}"
    admin_url = postgres_container.get_connection_url()
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
async def db_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine_for(postgres_url)
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


# Committed (not rolled back) database, for workers, queues and streams that use their own
# connections. Each test gets its own migrated database.
@pytest.fixture
async def committed_engine(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> AsyncIterator[AsyncEngine]:
    command.upgrade(make_alembic_config(fresh_database_url), "head")
    engine = create_engine_for(fresh_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def sessions(committed_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return session_factory(committed_engine)


@pytest.fixture
def database_url(fresh_database_url: str, committed_engine: AsyncEngine) -> str:
    return fresh_database_url


# ---- profile workflow harness (shared by workflow and API tests) --------------------------
sys.path.insert(0, str(Path(__file__).parent / "workflow" / "profile"))
from typing import Any  # noqa: E402

from harness import PROMPTS, Harness  # noqa: E402
from langgraph.checkpoint.base import BaseCheckpointSaver  # noqa: E402

from hiretitan.platform.llm.fake import FakeLlm  # noqa: E402
from hiretitan.platform.llm.prompts import PromptRegistry  # noqa: E402
from hiretitan.platform.runtime.checkpointer import open_checkpointer  # noqa: E402
from hiretitan.platform.runtime.runner import WorkflowRunner  # noqa: E402
from hiretitan.platform.storage.local import LocalFileStorage  # noqa: E402
from hiretitan.profile.workflow.graph import IngestDeps, profile_ingest_workflow  # noqa: E402


@pytest.fixture
async def profile_saver(database_url: str) -> AsyncIterator[BaseCheckpointSaver[Any]]:
    async with open_checkpointer(database_url) as checkpointer:
        yield checkpointer


@pytest.fixture
def make_harness(
    sessions: async_sessionmaker[AsyncSession],
    profile_saver: BaseCheckpointSaver[Any],
    tmp_path: Path,
):  # type: ignore[no-untyped-def]
    def build(script: list[Any] | None = None) -> Harness:
        storage = LocalFileStorage(tmp_path / "data")
        llm = FakeLlm(script or [])
        published: list[tuple[str, dict[str, Any]]] = []

        async def publish(event: str, data: dict[str, Any]) -> None:
            published.append((event, data))

        deps = IngestDeps(
            sessions=sessions,
            storage=storage,
            llm=llm,
            provider="fake",
            model="fake-model",
            prompts=PromptRegistry(PROMPTS),
            publish=publish,
        )
        runner = WorkflowRunner(
            sessions, profile_saver, {"profile_ingest": profile_ingest_workflow(deps)}
        )
        return Harness(sessions, storage, llm, runner, deps, published)

    return build
