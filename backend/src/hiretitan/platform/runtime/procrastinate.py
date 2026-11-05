"""The Procrastinate job queue on the app's own Postgres database.

``create_runtime`` builds the app and registers the tasks. Tasks reach the runner
through a ``RunnerHolder`` that ``worker_main`` fills once the checkpointer is open, so
importing this module needs no database.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import procrastinate
from procrastinate import JobContext
from procrastinate.retry import BaseRetryStrategy, RetryDecision

from hiretitan.platform.llm.provider_status import ProviderStatusService
from hiretitan.platform.runtime.checkpointer import psycopg_conninfo
from hiretitan.platform.runtime.runner import (
    RETRY_DELAYS_SECONDS,
    WorkflowRunner,
    retry_delay_seconds,
)

RUN_WORKFLOW_TASK = "run_workflow"
CHECK_PROVIDER_KEY_TASK = "check_provider_key"
MAX_ATTEMPTS = len(RETRY_DELAYS_SECONDS) + 1


class RunRetry(BaseRetryStrategy):
    """Retry after 10 s, 1 min and 5 min, then let the runner mark the run failed."""

    max_attempts = MAX_ATTEMPTS

    def get_retry_decision(
        self, *, exception: BaseException, job: procrastinate.jobs.Job
    ) -> RetryDecision | None:
        delay = retry_delay_seconds(job.attempts + 1)
        return None if delay is None else RetryDecision(retry_in={"seconds": delay})


@dataclass
class RunnerHolder:
    runner: WorkflowRunner | None = None

    def get(self) -> WorkflowRunner:
        if self.runner is None:
            raise RuntimeError("The workflow runner is not ready: the worker has not started")
        return self.runner


@dataclass
class ProcrastinateQueue:
    """``RunQueue`` backed by Procrastinate."""

    app: procrastinate.App

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        await self.app.configure_task(RUN_WORKFLOW_TASK).defer_async(
            run_id=str(run_id), resume=resume
        )


@dataclass
class Runtime:
    app: procrastinate.App
    holder: RunnerHolder = field(default_factory=RunnerHolder)
    provider_status: ProviderStatusService | None = None  # set by the composition root
    # Called after "Check again" finds the key working: puts runs paused for out_of_credit back
    # on the queue. The key check cannot see the credit balance, so a run that is still out of
    # credit simply pauses again with the provider's message.
    after_key_works: Callable[[], Awaitable[object]] | None = None

    @property
    def queue(self) -> ProcrastinateQueue:
        return ProcrastinateQueue(self.app)


def create_runtime(database_url: str) -> Runtime:
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=psycopg_conninfo(database_url))
    )
    runtime = Runtime(app)

    @app.task(name=RUN_WORKFLOW_TASK, pass_context=True, retry=RunRetry())
    async def run_workflow(context: JobContext, run_id: str, resume: Any = None) -> None:
        await runtime.holder.get().execute(
            UUID(run_id),
            resume=resume,
            attempt=context.job.attempts + 1,
            max_attempts=MAX_ATTEMPTS,
        )

    @app.task(name=CHECK_PROVIDER_KEY_TASK)
    async def check_provider_key() -> str:
        if runtime.provider_status is None:
            raise RuntimeError("Provider status is not set up: the worker has not started")
        status = await runtime.provider_status.check()
        if status == "working" and runtime.after_key_works is not None:
            await runtime.after_key_works()
        return status

    return runtime
