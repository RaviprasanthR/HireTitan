"""Worker composition root: ``python -m hiretitan.worker_main``.

Wires settings, the database, the AI platform, the checkpointer, the workflow registry and
the job queue; checks the AI key at start-up (resuming runs it had paused); then runs jobs
until stopped.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

from hiretitan import prompts as hiretitan_prompts
from hiretitan.drafts.workflow.common import DraftDeps
from hiretitan.drafts.workflow.outreach import OUTREACH_WORKFLOW, outreach_workflow
from hiretitan.drafts.workflow.tailor import TAILOR_WORKFLOW, tailor_workflow
from hiretitan.drafts_wiring import SqlJobs, SqlProfileFacts, tech_terms
from hiretitan.mail.workflow.ai_read import MailAiDeps
from hiretitan.mail.workflow.check import MAIL_CHECK_WORKFLOW, CheckDeps, mail_check_workflow
from hiretitan.mail.workflow.schedule import ScheduleDeps, daily_tick
from hiretitan.mail_wiring import build_check_deps, chain_mail_after_search
from hiretitan.platform.clock import SystemClock
from hiretitan.platform.config.settings import Settings, get_settings
from hiretitan.platform.db import create_engine, session_factory
from hiretitan.platform.llm.factory import build_llm
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.runtime.checkpointer import open_checkpointer
from hiretitan.platform.runtime.events import EventPublisher, run_notifier
from hiretitan.platform.runtime.procrastinate import Runtime, create_runtime
from hiretitan.platform.runtime.resume_paused import resume_after_key_works, resume_on_startup
from hiretitan.platform.runtime.runner import WorkflowDef, WorkflowRunner
from hiretitan.platform.security.logging import configure_logging
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.preferences.infra.repo import default_country_provider
from hiretitan.profile.workflow.graph import WORKFLOW_NAME, IngestDeps, profile_ingest_workflow
from hiretitan.search.application.synonyms_seed import load_title_synonyms
from hiretitan.search.application.tables_seed import load_seed_tables
from hiretitan.search.infra.careers_page.fetcher import CareersPageFetcher
from hiretitan.search.workflow.graph import WORKFLOW_NAME as SEARCH_WORKFLOW_NAME
from hiretitan.search.workflow.graph import SearchDeps, job_search_workflow
from hiretitan.search.workflow.judge import JudgeDeps
from hiretitan.search.workflow.recheck import RECHECK_WORKFLOW, recheck_workflow
from hiretitan.search_wiring import build_career_ops, build_descriptions, profile_card_source
from hiretitan.seed_dir import resolve_seed_dir

SEED_DIR = resolve_seed_dir()


def workflow_registry(
    deps: IngestDeps,
    search: SearchDeps,
    drafts: DraftDeps | None = None,
    mail: CheckDeps | None = None,
) -> Mapping[str, WorkflowDef]:
    """Every workflow this install can run, by name. Features add theirs here."""
    registry: dict[str, WorkflowDef] = {
        WORKFLOW_NAME: profile_ingest_workflow(deps),
        SEARCH_WORKFLOW_NAME: job_search_workflow(search),
        RECHECK_WORKFLOW: recheck_workflow(search),
    }
    if mail is not None:
        registry[MAIL_CHECK_WORKFLOW] = mail_check_workflow(mail)
    if drafts is not None:
        registry[OUTREACH_WORKFLOW] = outreach_workflow(drafts)
        registry[TAILOR_WORKFLOW] = tailor_workflow(drafts)
    return registry


async def _tick_at_start(runtime: Runtime) -> None:
    """A check overdue after days off happens soon after starting (FR-021); never stops start-up."""
    if runtime.mail_tick is None:
        return
    try:
        await runtime.mail_tick()
    except Exception:
        logging.getLogger(__name__).warning("The mail tick at start-up failed.", exc_info=True)


async def run_worker(settings: Settings, *, wait: bool = True) -> None:
    engine = create_engine(settings.database_url)
    sessions = session_factory(engine)
    publisher = EventPublisher(engine)
    runtime: Runtime = create_runtime(settings.database_url)
    built = build_llm(settings, sessions, publisher.publish)
    runtime.provider_status = built.provider_status

    async def requeue_paused() -> int:
        # every run a key problem paused: out of credit, and a missing or rejected key that was
        # then saved in Settings (no restart, FR-030)
        return await resume_after_key_works(sessions, runtime.queue)

    runtime.after_key_works = requeue_paused
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
    tables = load_seed_tables(SEED_DIR)  # area and technology tables; a bad file stops start-up
    pages = CareersPageFetcher(settings.data_dir / "cache" / "careers_pages")
    search_deps = SearchDeps(
        sessions=sessions,
        career_ops=build_career_ops(settings),
        clock=SystemClock(),
        synonyms=load_title_synonyms(SEED_DIR / "title_synonyms.yaml"),
        tech_names=tables.tech_names,
        publish=publisher.publish,
        pages=pages,
        descriptions=build_descriptions(settings, pages),  # one fetcher: one spacing per host
        page_ai=True,  # T053 eval passed 2026-11-08 (precision and recall 100%, 0 off-site links)
        judge=JudgeDeps(
            sessions=sessions,
            llm=built.llm,
            profile_card=profile_card_source(sessions, tables.tech_names),
            prompts=ingest_deps.prompts,
            provider=provider,
        ),
    )
    draft_deps = DraftDeps(
        sessions=sessions,
        llm=built.llm,
        prompts=ingest_deps.prompts,
        profile=SqlProfileFacts(sessions),
        jobs=SqlJobs(sessions),
        clock=SystemClock(),
        publish=publisher.publish,
        tech_terms=tech_terms(tables.tech_names),
        provider=provider,
    )
    mail_deps = build_check_deps(
        settings,
        sessions,
        SystemClock(),
        publisher.publish,
        search_deps.synonyms,
        tables.tech_names,
        lambda run_id: runtime.queue.enqueue(run_id),
        # unknown alert layouts are read by the AI (FR-013a); no key: they wait for the next check
        MailAiDeps(
            sessions=sessions, llm=built.llm, prompts=ingest_deps.prompts, provider=provider
        ),
    )
    schedule = ScheduleDeps(sessions=sessions, runs=mail_deps.runs, clock=SystemClock())

    async def mail_tick() -> object:
        return await daily_tick(schedule)

    runtime.mail_tick = mail_tick
    try:
        async with open_checkpointer(settings.database_url) as checkpointer:
            runtime.holder.runner = WorkflowRunner(
                sessions,
                checkpointer,
                workflow_registry(ingest_deps, search_deps, draft_deps, mail_deps),
                # a finished company search is followed by a mail check (Search now, FR-021)
                chain_mail_after_search(run_notifier(publisher), sessions, schedule),
            )
            async with runtime.app.open_async():
                await resume_on_startup(built.provider_status, sessions, runtime.queue)
                await _tick_at_start(runtime)
                await runtime.app.run_worker_async(wait=wait)
    finally:
        await engine.dispose()


def main() -> None:
    configure_logging(get_settings().secrets())
    if sys.platform == "win32":
        # psycopg's async mode can't run on Windows' default Proactor loop.
        asyncio.run(run_worker(get_settings()), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_worker(get_settings()))


if __name__ == "__main__":
    main()
