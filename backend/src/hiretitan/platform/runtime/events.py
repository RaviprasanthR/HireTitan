"""Server events over Postgres ``NOTIFY``/``LISTEN`` (contracts/rest-api.md, Events).

The worker and the API are separate processes, so events travel through the database.
Event types: ``run.updated``, ``status.updated``, ``profile.updated``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Final

from psycopg import AsyncConnection
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from hiretitan.platform.runtime.checkpointer import psycopg_conninfo
from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import Notify

CHANNEL: Final = "hiretitan_events"
EVENT_TYPES: Final = frozenset(
    {"run.updated", "status.updated", "profile.updated", "search.batch_done", "search.finished"}
)


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    data: dict[str, Any]


class EventPublisher:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        if event not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event}")
        payload = json.dumps({"event": event, "data": data})
        async with self._engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": CHANNEL, "payload": payload},
            )


def run_payload(run: Run) -> dict[str, Any]:
    state = run.state
    return {
        "run_id": str(run.id),
        "workflow": run.workflow,
        "status": state.status.value,
        "current_step": run.current_step,
        "pause_reason": state.pause_reason.value if state.pause_reason else None,
        "waiting_for": state.waiting_for.value if state.waiting_for else None,
    }


def run_notifier(publisher: EventPublisher) -> Notify:
    """A ``Notify`` for the runner: publish ``run.updated`` on every status change."""

    async def notify(run: Run) -> None:
        await publisher.publish("run.updated", run_payload(run))

    return notify


@asynccontextmanager
async def listen(database_url: str) -> AsyncIterator[AsyncIterator[Event]]:
    """Subscribe, then hand back the event iterator; the subscription is live on entry."""
    async with await AsyncConnection.connect(
        psycopg_conninfo(database_url), autocommit=True
    ) as conn:
        await conn.execute(f"LISTEN {CHANNEL}")

        async def events() -> AsyncIterator[Event]:
            async for notice in conn.notifies():
                message = json.loads(notice.payload)
                yield Event(message["event"], message["data"])

        yield events()
