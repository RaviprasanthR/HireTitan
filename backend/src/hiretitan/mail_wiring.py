"""Composition root for mail (feature 002c): where ``hiretitan.mail`` meets the rest of the app."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.connection import ConnectionService, Publish
from hiretitan.mail.application.consents import PendingConsents
from hiretitan.mail.application.ports import (
    CheckNotReadyError,
    GoogleAuth,
    MailboxProfile,
    MailReader,
    ReadEmail,
    SinkCounts,
    StartedCheck,
)
from hiretitan.mail.domain.links import clean_link
from hiretitan.mail.domain.senders import window_start
from hiretitan.mail.infra.fake_gmail import FakeGmail
from hiretitan.mail.infra.fake_google import FakeGoogle
from hiretitan.mail.infra.gmail_client import GmailClient, GmailProfile
from hiretitan.mail.infra.google_oauth import GoogleOAuth
from hiretitan.mail.infra.models import MailReadMessageRow
from hiretitan.mail.infra.repos import (
    ConnectionRepo,
    MailChecksRepo,
    ReadMessagesRepo,
    SendersRepo,
)
from hiretitan.mail.infra.secrets_file import SecretsFile
from hiretitan.mail.infra.seed import load_seed
from hiretitan.mail.infra.store import SqlMailStore
from hiretitan.mail.workflow.check import CheckDeps
from hiretitan.mail.workflow.schedule import ScheduleDeps, after_company_search
from hiretitan.platform.clock import ClockPort
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import Notify
from hiretitan.search.api.runs import MailPipelineOut, MailRunOut, MailUnreadableOut
from hiretitan.search.application.alerts import AlertPosting, store_alert_postings
from hiretitan.search.application.search import SearchAlreadyRunningError
from hiretitan.search.domain.rules_serialization import rules_from_dict
from hiretitan.search.domain.tech_names import TechTable
from hiretitan.search.infra.models import AlertSightingRow, JobRow, RelevanceDecisionRow
from hiretitan.search.infra.repos import RuleSetsRepo, SearchRunsRepo
from hiretitan.search.infra.search_store import WORKFLOW as SEARCH_WORKFLOW
from hiretitan.search.infra.search_store import AlertSearchStore

_log = logging.getLogger(__name__)


async def seed_mail_senders(sessions: async_sessionmaker[AsyncSession], path: Path) -> int:
    """Load the shipped sender list at start-up; no file means nothing to load. Returns how many
    addresses were new. A bad file stops start-up, like the other shipped tables."""
    if not await asyncio.to_thread(path.exists):
        return 0
    seed = await asyncio.to_thread(load_seed, path)
    async with sessions() as session:
        added = await SendersRepo(session).merge_seed(seed)
        await session.commit()
        return added


def _secrets_file(settings: Settings) -> SecretsFile:
    return SecretsFile(settings.data_dir / "secrets" / "gmail.json", os.environ)


def build_reader(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    publish: Publish,
) -> MailReader:
    """The mailbox a check reads: scripted synthetic mail for the e2e stack, else real Gmail.
    When Gmail refuses the saved access the connection is marked "reconnect" (FR-005)."""
    if settings.mail == "fake":
        if settings.fake_gmail_dir is None:
            raise ValueError("HIRETITAN_MAIL=fake needs HIRETITAN_FAKE_GMAIL_DIR.")
        return FakeGmail(settings.fake_gmail_dir)
    store = SqlMailStore(sessions)

    async def access_ended(message: str) -> None:
        await store.set_state("needs_reconnect", message[:300])
        try:
            await publish("mail.connection_changed", {"state": "needs_reconnect"})
        except Exception:  # an event only refreshes the page
            return

    return GmailClient(
        auth=GoogleOAuth(), secrets=_secrets_file(settings), on_access_ended=access_ended
    )


def build_check_deps(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    clock: ClockPort,
    publish: Publish,
    synonyms: Mapping[str, tuple[str, ...]],
    tech_names: TechTable,
    enqueue: Callable[[UUID], Awaitable[None]],
) -> CheckDeps:
    """Everything the worker's mail check needs."""
    return CheckDeps(
        sessions=sessions,
        reader=build_reader(settings, sessions, publish),
        sink=SqlAlertSink(sessions, synonyms, tech_names),
        runs=SqlCheckRuns(sessions, enqueue),
        clock=clock,
        publish=publish,
    )


def chain_mail_after_search(
    notify: Notify,
    sessions: async_sessionmaker[AsyncSession],
    schedule: ScheduleDeps,
) -> Notify:
    """Wrap the runner's notice: when a company search has finished (not stopped, not failed),
    Gmail is read too (FR-021, "Search now"). The mail check starts only after the search run is
    marked done, because only one search may be active at a time."""

    async def wrapped(run: Run) -> None:
        await notify(run)
        if run.workflow != SEARCH_WORKFLOW or run.state.status is not RunStatus.done:
            return
        try:
            async with sessions() as session:
                search_run = await SearchRunsRepo(session).by_workflow_run(run.id)
            if search_run is None or search_run.outcome != "finished":
                return
            await after_company_search(schedule)
        except Exception:
            # the search itself is done and its result stands; reading mail is a bonus
            _log.warning("Could not start the mail check after a search.", exc_info=True)

    return wrapped


def make_stop_check(
    sessions: async_sessionmaker[AsyncSession], *, wait_seconds: float = 30.0
) -> Callable[[], Awaitable[None]]:
    """Disconnect first asks a running mail check to stop and waits for it to end (FR-004)."""

    async def stop_running_check() -> None:
        async with sessions() as session:
            run = await SearchRunsRepo(session).active()
            if run is None or run.mode != "mail_alerts":
                return
            run_id = run.id
            await SearchRunsRepo(session).request_stop(run_id)
            await session.commit()
        for _ in range(int(wait_seconds / 0.25)):
            async with sessions() as session:
                run = await SearchRunsRepo(session).get(run_id)
                if run is None or run.outcome is not None:
                    return
            await asyncio.sleep(0.25)

    return stop_running_check


def build_connection_service(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    clock: ClockPort,
    publish: Publish,
    stop_check: Callable[[], Awaitable[None]] | None = None,
) -> ConnectionService:
    """The connection use cases over real Google, or the scripted one (``HIRETITAN_MAIL=fake``)."""
    auth: GoogleAuth
    profile: MailboxProfile
    if settings.mail == "fake":
        if settings.fake_gmail_dir is None:
            raise ValueError("HIRETITAN_MAIL=fake needs HIRETITAN_FAKE_GMAIL_DIR.")
        fake = FakeGoogle(settings.fake_gmail_dir)
        auth, profile = fake, fake
    else:
        auth, profile = GoogleOAuth(), GmailProfile()
    return ConnectionService(
        store=SqlMailStore(sessions),
        secrets=_secrets_file(settings),
        auth=auth,
        profile=profile,
        consents=PendingConsents(clock),
        clock=clock,
        redirect_uri=f"http://localhost:{settings.port}/api/v1/mail/google/callback",
        stop_check=stop_check or make_stop_check(sessions),
        publish=publish,
    )


class SqlAlertSink:
    """Records a batch of read emails and stores their jobs through the search module, in one
    transaction (``AlertBatchSink``). This is the one place the mail and search tables meet."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        synonyms: Mapping[str, tuple[str, ...]],
        tech_names: TechTable,
    ) -> None:
        self._sessions = sessions
        self._synonyms = synonyms
        self._tech_names = tech_names

    async def store(
        self,
        *,
        search_run_id: UUID,
        mail_check_id: UUID,
        batch_no: int,
        emails: Sequence[ReadEmail],
        now: datetime,
    ) -> SinkCounts:
        async with self._sessions() as session:
            run = await SearchRunsRepo(session).get(search_run_id)
            if run is None or await ConnectionRepo(session).get() is None:
                # Delete all my data or Disconnect happened while this check was running: nothing
                # may be written back (the read-email records, the jobs) after the person said no
                return SinkCounts()
            rule_set = await RuleSetsRepo(session).get(run.rule_set_id)
            if rule_set is None:
                return SinkCounts()
            reads = ReadMessagesRepo(session)
            postings: list[AlertPosting] = []
            for email in emails:
                message_id = await reads.record(
                    email.message_id,
                    email.sender,
                    email.received_at,
                    email.outcome,
                    email.reader,
                    len(email.jobs),
                    email.injection_signals,
                    mail_check_id,
                    now,
                )
                postings.extend(
                    AlertPosting(
                        title=job.title,
                        company=job.company,
                        location=job.location,
                        link=job.link,
                        clean_link=clean_link(job.site, job.link),
                        posting_id=job.posting_id,
                        site=job.site,
                        alert_date=job.alert_date,
                        posted_at=job.posted_at,
                        injection_signals=email.injection_signals,
                        read_message_id=message_id,
                    )
                    for job in email.jobs
                )
            counts = await store_alert_postings(
                AlertSearchStore(session),  # commits the read records and the jobs together
                search_run_id=search_run_id,
                batch_no=batch_no,
                postings=postings,
                rules=rules_from_dict(rule_set.rules),
                synonyms=self._synonyms,
                tech_names=self._tech_names,
                now=now,
            )
        return SinkCounts(
            new=counts.new,
            already_known=counts.already_known,
            left_out=counts.left_out,
            already_in_pipeline=counts.already_in_pipeline,
            possible_duplicates=counts.possible_duplicates,
            in_pipeline_titles=counts.in_pipeline_titles,
        )


class SqlCheckRuns:
    """A mail check as a search run: creates it, finds it again, and ends it (``CheckRuns``)."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        enqueue: Callable[[UUID], Awaitable[None]],
    ) -> None:
        self._sessions = sessions
        self._enqueue = enqueue

    async def start(self, *, trigger: str, now: datetime) -> StartedCheck:
        async with self._sessions() as session:
            connection = await ConnectionRepo(session).get()
            if connection is None:
                raise CheckNotReadyError("not_connected")
            if connection.state != "connected":
                raise CheckNotReadyError("needs_reconnect")
            approved = await RuleSetsRepo(session).approved()
            if approved is None:
                raise CheckNotReadyError("no_rules")
            store = AlertSearchStore(session)
            if await store.active_search_exists():
                raise CheckNotReadyError("search_running")
            try:
                started = await store.create_run(approved.id, "mail_alerts", now)
            except SearchAlreadyRunningError as error:
                raise CheckNotReadyError("search_running") from error
            window = window_start(now)
            check = await MailChecksRepo(session).create(started.search_run_id, trigger, window)
            await session.commit()
        await self._enqueue(started.run_id)
        return StartedCheck(started.search_run_id, check.id, window)

    async def locate(self, workflow_run_id: UUID) -> StartedCheck | None:
        async with self._sessions() as session:
            run = await SearchRunsRepo(session).by_workflow_run(workflow_run_id)
            if run is None:
                return None
            check = await MailChecksRepo(session).get_for_run(run.id)
            if check is None:
                return None
            return StartedCheck(run.id, check.id, check.window_start)

    async def stop_requested(self, search_run_id: UUID) -> bool:
        async with self._sessions() as session:
            run = await SearchRunsRepo(session).get(search_run_id)
            return bool(run and run.stop_requested)

    async def finish(
        self, search_run_id: UUID, *, outcome: str, message: str | None, now: datetime
    ) -> None:
        async with self._sessions() as session:
            await SearchRunsRepo(session).finish(
                search_run_id, outcome=outcome, finished_at=now, stop_message=message
            )
            await session.commit()


async def mail_run_details(session: AsyncSession, search_run_id: UUID) -> MailRunOut | None:
    """The mail numbers of a check, for ``GET /search/runs*`` (search never imports mail)."""
    check = await MailChecksRepo(session).get_for_run(search_run_id)
    if check is None:
        return None
    rows = await session.execute(
        select(
            MailReadMessageRow.sender,
            MailReadMessageRow.received_at,
            MailReadMessageRow.outcome,
        )
        .where(
            MailReadMessageRow.mail_check_id == check.id,
            MailReadMessageRow.outcome.in_(("unreadable", "needs_ai", "no_jobs")),
        )
        .order_by(MailReadMessageRow.received_at.desc())
        .limit(50)
    )
    # jobs this check left out because the person already has them in the pipeline, and jobs in
    # the pipeline that an email of this check showed again (same link); deleted jobs never count
    left_out = (
        select(JobRow.id)
        .join(RelevanceDecisionRow, RelevanceDecisionRow.job_id == JobRow.id)
        .where(
            RelevanceDecisionRow.search_run_id == search_run_id,
            RelevanceDecisionRow.rule_key == "already_in_pipeline",
        )
    )
    sighted = (
        select(AlertSightingRow.job_id)
        .join(MailReadMessageRow, MailReadMessageRow.id == AlertSightingRow.read_message_id)
        .where(MailReadMessageRow.mail_check_id == check.id)
    )
    pipeline = await session.execute(
        select(JobRow.id, JobRow.title, JobRow.company_name)
        .where(
            JobRow.state != "deleted",
            or_(
                JobRow.id.in_(left_out),
                and_(JobRow.state.in_(("applied", "inquired")), JobRow.id.in_(sighted)),
            ),
        )
        .order_by(JobRow.title, JobRow.id)
        .limit(200)
    )
    return MailRunOut(
        trigger=check.trigger,
        window_start=check.window_start,
        emails_listed=check.emails_listed,
        emails_skipped=check.emails_skipped,
        emails_read=check.emails_read,
        emails_unreadable=check.emails_unreadable,
        more_remaining=check.more_remaining,
        ended=check.ended,
        unreadable=[
            MailUnreadableOut(sender=r.sender, received_at=r.received_at, why=r.outcome)
            for r in rows
        ],
        already_in_pipeline=[
            MailPipelineOut(job_id=r.id, title=r.title, company=r.company_name) for r in pipeline
        ],
    )
