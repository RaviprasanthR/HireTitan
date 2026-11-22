"""When a mail check starts on its own (feature 002c, FR-021, US5 AS1).

Two things start one: an hourly tick that checks once 24 hours have passed since the last check
(the same tick runs once when the worker starts, so a check overdue after days off happens soon
after starting), and the end of a company search ("Search now" reads mail too).

Neither is ever an error. A check that cannot start now (not connected, access ended, a search or
another check is running, rules not approved yet) is simply not started; the next tick tries again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.ports import CheckNotReadyError, CheckRuns
from hiretitan.mail.infra.repos import ConnectionRepo
from hiretitan.platform.clock import ClockPort

_log = logging.getLogger(__name__)

WINDOW: Final = timedelta(hours=24)


@dataclass(frozen=True)
class ScheduleDeps:
    sessions: async_sessionmaker[AsyncSession]
    runs: CheckRuns
    clock: ClockPort


async def _last_check_if_connected(deps: ScheduleDeps) -> tuple[bool, datetime | None]:
    """(is Gmail connected and working, when the last check started or None)."""
    async with deps.sessions() as session:
        connection = await ConnectionRepo(session).get()
    if connection is None or connection.state != "connected":
        return False, None
    return True, connection.last_check_started_at


async def _start(deps: ScheduleDeps, trigger: str) -> UUID | None:
    try:
        started = await deps.runs.start(trigger=trigger, now=deps.clock.now())
    except CheckNotReadyError as error:
        _log.info("Mail check not started (%s): %s", trigger, error.reason)
        return None
    return started.search_run_id


async def daily_tick(deps: ScheduleDeps) -> UUID | None:
    """Start a ``daily`` check when connected and the last one began 24 hours ago or more (or
    there never was one). Returns the new check's run id, or None when nothing was started."""
    connected, last = await _last_check_if_connected(deps)
    if not connected:
        return None
    if last is not None and deps.clock.now() - last < WINDOW:
        return None
    return await _start(deps, "daily")


async def after_company_search(deps: ScheduleDeps) -> UUID | None:
    """Start a ``search_now`` check (Search now reads mail too), whatever the last check's age."""
    connected, _ = await _last_check_if_connected(deps)
    if not connected:
        return None
    return await _start(deps, "search_now")
