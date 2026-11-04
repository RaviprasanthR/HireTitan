"""Worker composition root: ``python -m hiretitan.worker_main``.

Wires settings, the database, the checkpointer, the workflow registry and the job queue,
then runs jobs until stopped.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping

from hiretitan.platform.config.settings import Settings, get_settings
from hiretitan.platform.db import create_engine, session_factory
from hiretitan.platform.runtime.checkpointer import open_checkpointer
from hiretitan.platform.runtime.events import EventPublisher, run_notifier
from hiretitan.platform.runtime.procrastinate import Runtime, create_runtime
from hiretitan.platform.runtime.runner import WorkflowDef, WorkflowRunner


def workflow_registry() -> Mapping[str, WorkflowDef]:
    """Every workflow this install can run, by name. Features add theirs here."""
    return {}


async def run_worker(settings: Settings, *, wait: bool = True) -> None:
    engine = create_engine(settings.database_url)
    publisher = EventPublisher(engine)
    runtime: Runtime = create_runtime(settings.database_url)
    try:
        async with open_checkpointer(settings.database_url) as checkpointer:
            runtime.holder.runner = WorkflowRunner(
                session_factory(engine),
                checkpointer,
                workflow_registry(),
                run_notifier(publisher),
            )
            async with runtime.app.open_async():
                await runtime.app.run_worker_async(wait=wait)
    finally:
        await engine.dispose()


def main() -> None:
    if sys.platform == "win32":
        # psycopg's async mode can't run on Windows' default Proactor loop.
        asyncio.run(run_worker(get_settings()), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_worker(get_settings()))


if __name__ == "__main__":
    main()
