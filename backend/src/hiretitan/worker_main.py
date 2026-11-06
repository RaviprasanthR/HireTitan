"""Worker composition root: ``python -m hiretitan.worker_main``.

Wires settings, the database, the AI platform, the checkpointer, the workflow registry and
the job queue; checks the AI key at start-up (resuming runs it had paused); then runs jobs
until stopped.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping
from pathlib import Path

from hiretitan import prompts as hiretitan_prompts
from hiretitan.platform.clock import SystemClock
from hiretitan.platform.config.settings import Settings, get_settings
from hiretitan.platform.db import create_engine, session_factory
from hiretitan.platform.llm.factory import build_llm
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.runtime.checkpointer import open_checkpointer
from hiretitan.platform.runtime.domain.run_state import PauseReason
from hiretitan.platform.runtime.events import EventPublisher, run_notifier
from hiretitan.platform.runtime.procrastinate import Runtime, create_runtime
from hiretitan.platform.runtime.resume_paused import resume_on_startup, resume_paused_runs
from hiretitan.platform.runtime.runner import WorkflowDef, WorkflowRunner
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.preferences.infra.repo import default_country_provider
from hiretitan.profile.workflow.graph import WORKFLOW_NAME, IngestDeps, profile_ingest_workflow
from hiretitan.search.application.synonyms_seed import load_title_synonyms
from hiretitan.search.workflow.graph import WORKFLOW_NAME as SEARCH_WORKFLOW_NAME
from hiretitan.search.workflow.graph import SearchDeps, job_search_workflow
from hiretitan.search.workflow.judge import JudgeDeps
from hiretitan.search.workflow.recheck import RECHECK_WORKFLOW, recheck_workflow
from hiretitan.search_wiring import build_career_ops, profile_card_source
from hiretitan.setup.infra.settings_repo import budget_cap_provider

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


def workflow_registry(deps: IngestDeps, search: SearchDeps) -> Mapping[str, WorkflowDef]:
    """Every workflow this install can run, by name. Features add theirs here."""
    return {
        WORKFLOW_NAME: profile_ingest_workflow(deps),
        SEARCH_WORKFLOW_NAME: job_search_workflow(search),
        RECHECK_WORKFLOW: recheck_workflow(search),
    }


async def run_worker(settings: Settings, *, wait: bool = True) -> None:
    engine = create_engine(settings.database_url)
    sessions = session_factory(engine)
    publisher = EventPublisher(engine)
    runtime: Runtime = create_runtime(settings.database_url)
    built = build_llm(
        settings, sessions, budget_cap_provider(sessions), SystemClock(), publisher.publish
    )
    runtime.provider_status = built.provider_status

    async def requeue_out_of_credit() -> int:
        return await resume_paused_runs(sessions, runtime.queue, PauseReason.out_of_credit)

    runtime.after_key_works = requeue_out_of_credit
    provider = "fake" if settings.llm == "fake" else "openai"
    ingest_deps = IngestDeps(
        sessions=sessions,
        storage=LocalFileStorage(settings.data_dir),
        llm=built.llm,
        provider=provider,
        model=ModelCatalog.load().model_for(provider, "fast"),
        prompts=PromptRegistry(Path(hiretitan_prompts.__file__).parent),
        publish=publisher.publish,
        default_country=default_country_provider(sessions),
    )
    search_deps = SearchDeps(
        sessions=sessions,
        career_ops=build_career_ops(settings),
        clock=SystemClock(),
        synonyms=load_title_synonyms(SEED_DIR / "title_synonyms.yaml"),
        publish=publisher.publish,
        judge=JudgeDeps(
            sessions=sessions,
            llm=built.llm,
            profile_card=profile_card_source(sessions),
            prompts=ingest_deps.prompts,
            provider=provider,
        ),
    )
    try:
        async with open_checkpointer(settings.database_url) as checkpointer:
            runtime.holder.runner = WorkflowRunner(
                sessions,
                checkpointer,
                workflow_registry(ingest_deps, search_deps),
                run_notifier(publisher),
            )
            async with runtime.app.open_async():
                await resume_on_startup(built.provider_status, sessions, runtime.queue)
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
