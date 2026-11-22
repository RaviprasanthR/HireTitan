"""The mail check: read the last 24 hours of alert mail from the enabled senders, once each, and
hand the jobs to the search module (feature 002c, US2; research R2, R8, R13).

A check is a search run in the mode ``mail_alerts``. This workflow lists the matching messages
(at most 200, FR-012), skips those already read (FR-011), reads the rest in batches of 20, and for
each batch records the emails and stores their jobs in one transaction. Stop is looked for between
batches and once more at the end (FR-010). It ends with the counts, which add up (FR-026).

Untrusted mail (constitution III): the email is flattened in memory, screened, and dropped; no
subject, snippet or body is stored (FR-016). Nothing here calls an AI: only fixed readers run.

Whatever goes wrong, the check ends: Gmail refusing or not answering ends it with a reason, and
any other error ends it as failed, so a run is never left "running" and the next check can start.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Final, TypedDict
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.ports import (
    AlertBatchSink,
    CheckRuns,
    MailAccessEndedError,
    MailMessageNotFoundError,
    MailReader,
    MailUnavailableError,
    ReadEmail,
)
from hiretitan.mail.domain.mime import Flat, UnreadableMessageError, flatten_message
from hiretitan.mail.domain.readers import READERS, read_alert
from hiretitan.mail.domain.senders import build_query
from hiretitan.mail.infra.repos import (
    ConnectionRepo,
    MailChecksRepo,
    ReadMessagesRepo,
    SendersRepo,
)
from hiretitan.platform.clock import ClockPort
from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import WorkflowDef
from hiretitan.platform.untrusted.screen import screen

_log = logging.getLogger(__name__)

MAIL_CHECK_WORKFLOW: Final = "mail_check"
MESSAGES_MAX: Final = 200  # FR-012
BATCH_SIZE: Final = 20
LIST_PAGE: Final = 100
PAGES_MAX: Final = 5
NO_SENDER: Final = "unknown@invalid"
ERROR_MESSAGE: Final = "The check stopped because of an error."

Publish = Callable[[str, dict[str, Any]], Awaitable[None]]


class CheckState(TypedDict, total=False):
    run_id: str


@dataclass(frozen=True)
class CheckDeps:
    sessions: async_sessionmaker[AsyncSession]
    reader: MailReader
    sink: AlertBatchSink
    runs: CheckRuns
    clock: ClockPort
    publish: Publish | None = None
    # told when Gmail refuses the saved access (the connection is then marked "reconnect")
    on_access_ended: Callable[[str], Awaitable[None]] | None = None


@dataclass
class _Totals:
    listed: int = 0
    skipped: int = 0
    read: int = 0  # emails read, with jobs or none
    unreadable: int = 0
    more_remaining: bool = False
    emails: list[ReadEmail] = field(default_factory=list)
    batches: int = 0


class _Nothing(Exception):
    """No sender is on: the check ends at once with nothing listed."""


def _signals(flat: Flat) -> list[dict[str, Any]]:
    """Text in the email that looks like instructions to an AI (FR-014): flagged, never obeyed.

    Only which rule matched, how serious it is and where (visible or hidden) is kept. The email's
    own words are not stored (FR-016), so ``excerpt`` stays empty."""
    visible = screen("\n".join(line.text for line in flat.lines))
    hidden = screen("\n".join(flat.hidden), "hidden")
    return [
        {"rule_id": f.rule_id, "severity": f.severity, "excerpt": "", "location": f.location}
        for f in [*visible, *hidden]
    ]


def read_email(message_id: str, sender: str, received_at: Any, raw: bytes, site: str) -> ReadEmail:
    """One email in, what it yielded out. A built-in site whose reader finds nothing in a
    non-empty email is counted as unreadable (FR-017); an unlisted sender waits for the AI. An
    email with no trustworthy sender is unreadable and is never read for jobs."""
    if not sender:
        return ReadEmail(message_id, NO_SENDER, received_at, "unreadable", None, [], [])
    try:
        flat = flatten_message(raw)
    except UnreadableMessageError:
        return ReadEmail(message_id, sender, received_at, "unreadable", None, [], [])
    jobs = read_alert(site, flat, received_at)
    signals = _signals(flat)
    if jobs:
        return ReadEmail(message_id, sender, received_at, "read", site, jobs, signals)
    if not flat.lines and not flat.links:
        return ReadEmail(message_id, sender, received_at, "no_jobs", None, [], signals)
    outcome = "unreadable" if site in READERS else "needs_ai"
    return ReadEmail(message_id, sender, received_at, outcome, None, [], signals)


async def _publish(deps: CheckDeps, name: str, data: dict[str, Any]) -> None:
    """An event only refreshes the page: failing to send one never fails or repeats a check."""
    if deps.publish is None:
        return
    try:
        await deps.publish(name, data)
    except Exception:
        _log.warning("Could not publish %s.", name, exc_info=True)


async def _flush(deps: CheckDeps, state: _Totals, search_run_id: UUID, check_id: UUID) -> None:
    """Record the emails read so far, with their jobs, in one transaction; then the totals."""
    if not state.emails:
        return
    state.batches += 1
    counts = await deps.sink.store(
        search_run_id=search_run_id,
        mail_check_id=check_id,
        batch_no=state.batches,
        emails=state.emails,
        now=deps.clock.now(),
    )
    state.emails = []
    async with deps.sessions() as session:
        await MailChecksRepo(session).set_counts(
            check_id,
            listed=state.listed,
            skipped=state.skipped,
            read=state.read,
            unreadable=state.unreadable,
            more_remaining=state.more_remaining,
        )
        await session.commit()
    await _publish(
        deps,
        "search.batch_done",
        {
            "search_run_id": str(search_run_id),
            "emails_read": state.read,
            "emails_listed": state.listed,
            "added": counts.new,
        },
    )


async def _list_ids(deps: CheckDeps, query: str, totals: _Totals) -> list[str]:
    """The ids to look at: at most 200, in order, each once (a page can repeat an id when mail
    arrives meanwhile), and never more than a few pages (a broken answer cannot loop forever)."""
    ids: list[str] = []
    token: str | None = None
    for _page in range(PAGES_MAX):
        page = await deps.reader.list_ids(query, page_token=token, max_results=LIST_PAGE)
        ids = list(dict.fromkeys([*ids, *page.ids]))
        token = page.next_page_token
        if token is None or len(ids) >= MESSAGES_MAX:
            break
    totals.more_remaining = token is not None or len(ids) > MESSAGES_MAX
    return ids[:MESSAGES_MAX]


async def _read_one(
    deps: CheckDeps, totals: _Totals, message_id: str, site_of: dict[str, str], now: Any
) -> None:
    """Fetch and read one email. Only Gmail refusing or not answering stops the check; anything
    that goes wrong with this one email only makes it "could not be read"."""
    try:
        raw = await deps.reader.get_raw(message_id)
    except MailMessageNotFoundError:
        totals.unreadable += 1  # deleted since it was listed
        return
    except (MailAccessEndedError, MailUnavailableError):
        raise
    except UnreadableMessageError:
        totals.unreadable += 1
        totals.emails.append(ReadEmail(message_id, NO_SENDER, now, "unreadable", None, [], []))
        return
    except Exception:
        _log.warning("One email could not be fetched.", exc_info=True)
        totals.unreadable += 1
        return
    site = site_of.get(raw.sender, "other")
    try:
        # parsing up to 2 MB must not hold the worker's event loop
        email = await asyncio.to_thread(
            read_email, message_id, raw.sender, raw.received_at, raw.raw, site
        )
    except Exception:
        _log.warning("One email could not be read.", exc_info=True)
        email = ReadEmail(
            message_id, raw.sender or NO_SENDER, raw.received_at, "unreadable", None, [], []
        )
    totals.emails.append(email)
    if email.outcome in ("read", "no_jobs"):
        totals.read += 1
    else:
        totals.unreadable += 1


async def _finish(
    deps: CheckDeps,
    totals: _Totals,
    search_run_id: UUID,
    check_id: UUID,
    ended: str,
    outcome: str,
    message: str | None,
) -> None:
    async with deps.sessions() as session:
        await MailChecksRepo(session).finish(
            check_id,
            listed=totals.listed,
            skipped=totals.skipped,
            read=totals.read,
            unreadable=totals.unreadable,
            more_remaining=totals.more_remaining,
            ended=ended,
        )
        await session.commit()
    await deps.runs.finish(search_run_id, outcome=outcome, message=message, now=deps.clock.now())
    await _publish(
        deps,
        "search.finished",
        {"search_run_id": str(search_run_id), "outcome": outcome, "stop_message": message},
    )


async def run_check(deps: CheckDeps, state: CheckState) -> CheckState:
    workflow_run_id = UUID(state["run_id"])
    started = await deps.runs.locate(workflow_run_id)
    if started is None:
        return {}
    search_run_id, check_id = started.search_run_id, started.mail_check_id
    now = deps.clock.now()
    totals = _Totals()
    ended, outcome, message = "finished", "finished", None

    try:
        async with deps.sessions() as session:
            senders = [s for s in await SendersRepo(session).list_all() if s.enabled]
            site_of = {s.address: s.site for s in senders}
            await ConnectionRepo(session).mark_check_started(now)
            await session.commit()
        if not site_of:
            raise _Nothing
        ids = await _list_ids(deps, build_query(sorted(site_of), now), totals)
        totals.listed = len(ids)
        async with deps.sessions() as session:
            done = await ReadMessagesRepo(session).already_read(ids)
        totals.skipped = len(done)
        wanted = [i for i in ids if i not in done]

        for number, message_id in enumerate(wanted):
            if number % BATCH_SIZE == 0:  # a new batch: store the last one, then look for Stop
                await _flush(deps, totals, search_run_id, check_id)
                if await deps.runs.stop_requested(search_run_id):
                    ended, outcome = "stopped", "stopped_by_user"
                    totals.more_remaining = True
                    break
            await _read_one(deps, totals, message_id, site_of, now)
        else:
            await _flush(deps, totals, search_run_id, check_id)
            if await deps.runs.stop_requested(search_run_id):  # Stop during the last batch
                ended, outcome = "stopped", "stopped_by_user"
    except _Nothing:
        pass
    except MailAccessEndedError as error:
        ended, outcome, message = "access_ended", "failed", "Gmail access has ended."
        _log.warning("A mail check ended: Gmail access has ended.")
        if deps.on_access_ended is not None:
            await deps.on_access_ended(str(error))
    except MailUnavailableError:
        ended, outcome, message = "gmail_unavailable", "failed", "Gmail did not answer."
        _log.warning("A mail check ended: Gmail did not answer.")
    except Exception:
        # whatever else went wrong: the check ends as failed (never left "running", never retried
        # into the same failure) and the next one can start
        _log.exception("A mail check failed.")
        ended, outcome, message = "failed", "failed", ERROR_MESSAGE

    try:
        await _flush(deps, totals, search_run_id, check_id)
    except Exception:
        _log.exception("The last emails of a mail check could not be stored.")
        ended, outcome, message = "failed", "failed", ERROR_MESSAGE
    await _finish(deps, totals, search_run_id, check_id, ended, outcome, message)
    return {}


def mail_check_workflow(deps: CheckDeps) -> WorkflowDef:
    def build(saver: BaseCheckpointSaver[Any]) -> Any:
        graph = StateGraph(CheckState)
        graph.add_node("check", partial(run_check, deps))
        graph.add_edge(START, "check")
        graph.add_edge("check", END)
        return graph.compile(checkpointer=saver)

    def initial_input(run: Run) -> dict[str, Any]:
        return {"run_id": str(run.id)}

    async def on_failed(run: Run) -> None:
        """The runner gave up on this run: end its check as failed so it is never left running."""
        started = await deps.runs.locate(run.id)
        if started is None:
            return
        async with deps.sessions() as session:
            check = await MailChecksRepo(session).get(started.mail_check_id)
            if check is not None and check.ended is None:
                await MailChecksRepo(session).mark_failed(started.mail_check_id)
                await session.commit()
        await deps.runs.finish(
            started.search_run_id, outcome="failed", message=ERROR_MESSAGE, now=deps.clock.now()
        )

    return WorkflowDef(build=build, initial_input=initial_input, on_failed=on_failed)
