"""Delete-all retries when Postgres picks it as the victim of a deadlock with the worker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg.errors import DeadlockDetected
from sqlalchemy.exc import OperationalError

from hiretitan.setup_wiring import SqlDeleteAllStore


def _deadlock() -> OperationalError:
    return OperationalError("TRUNCATE", {}, DeadlockDetected("deadlock detected"))


async def test_wipe_is_tried_again_after_a_deadlock() -> None:
    session = MagicMock()
    session.rollback = AsyncMock()
    store = SqlDeleteAllStore(session)
    attempts = AsyncMock(side_effect=[_deadlock(), _deadlock(), None])
    store._wipe_once = attempts  # type: ignore[method-assign]

    await store.wipe_and_reseed()

    assert attempts.await_count == 3
    assert session.rollback.await_count == 2


async def test_wipe_gives_up_after_three_deadlocks() -> None:
    session = MagicMock()
    session.rollback = AsyncMock()
    store = SqlDeleteAllStore(session)
    store._wipe_once = AsyncMock(side_effect=[_deadlock(), _deadlock(), _deadlock()])  # type: ignore[method-assign]

    with pytest.raises(OperationalError):
        await store.wipe_and_reseed()


async def test_other_database_errors_are_not_retried() -> None:
    session = MagicMock()
    session.rollback = AsyncMock()
    store = SqlDeleteAllStore(session)
    attempts = AsyncMock(side_effect=OperationalError("TRUNCATE", {}, Exception("disk full")))
    store._wipe_once = attempts  # type: ignore[method-assign]

    with pytest.raises(OperationalError):
        await store.wipe_and_reseed()

    assert attempts.await_count == 1
