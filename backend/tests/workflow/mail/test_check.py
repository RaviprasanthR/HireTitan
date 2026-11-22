"""The mail check end to end (T025): US2 AS1-AS7, FR-005, FR-016, FR-017, FR-018, FR-018a.

Fake Gmail over the synthetic fixtures, real PostgreSQL, the real sink and run control. No AI is
wired anywhere: the check has no way to ask one (FR-018).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.ports import (
    MailAccessEndedError,
    MailMessageNotFoundError,
    MailUnavailableError,
    MessagePage,
    RawMessage,
)
from hiretitan.mail.infra.fake_gmail import FakeGmail
from hiretitan.mail.infra.models import MailCheckRow, MailReadMessageRow
from hiretitan.mail.infra.repos import ConnectionRepo
from hiretitan.mail.workflow.check import CheckDeps, run_check
from hiretitan.mail_wiring import SqlAlertSink, SqlCheckRuns, seed_mail_senders
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.domain.rules import RuleItem, SearchRules
from hiretitan.search.domain.rules_serialization import rules_to_dict
from hiretitan.search.infra.models import (
    AlertSightingRow,
    CompanyRow,
    JobRow,
    JobSourceRow,
    RelevanceDecisionRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import RuleSetsRepo, SearchRunsRepo

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mail"
SEED = Path(__file__).resolve().parents[3] / "seed" / "mail_senders.yaml"
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=IST)  # every "-01" fixture is inside the last 24 hours


class WatchedGmail(FakeGmail):
    """The fake Gmail, plus a log of every call and the means to make it fail."""

    def __init__(self, folder: Path) -> None:
        super().__init__(folder)
        self.queries: list[str] = []
        self.fetched: list[str] = []
        self.fail_on: dict[int, Exception] = {}
        self.pages: list[MessagePage] | None = None  # scripted list answers, taken in order
        self.on_fetch: Callable[[int], Awaitable[None]] | None = None

    async def list_ids(
        self, query: str, *, page_token: str | None = None, max_results: int = 100
    ) -> MessagePage:
        self.queries.append(query)
        if self.pages is not None:
            return self.pages.pop(0) if self.pages else MessagePage([], None)
        return await super().list_ids(query, page_token=page_token, max_results=max_results)

    async def get_raw(self, message_id: str) -> RawMessage:
        self.fetched.append(message_id)
        if self.on_fetch is not None:
            await self.on_fetch(len(self.fetched))
        if (error := self.fail_on.get(len(self.fetched))) is not None:
            raise error
        return await super().get_raw(message_id)


@dataclass
class Env:
    sessions: async_sessionmaker[AsyncSession]
    gmail: WatchedGmail
    deps: CheckDeps
    runs: SqlCheckRuns
    clock: FakeClock
    mailbox: Path
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    queued: list[UUID] = field(default_factory=list)
    access_ended: list[str] = field(default_factory=list)

    def add(self, *names: str, as_sender: str | None = None) -> None:
        """Copy fixture emails into the mailbox; ``as_sender`` re-addresses them and moves them
        into the 24-hour window (the unknown-layout digests are older than a day)."""
        for name in names:
            raw = (FIXTURES / "eml" / f"{name}.eml").read_text("utf-8")
            if as_sender:
                raw = "\n".join(
                    f"From: Alerts <{as_sender}>"
                    if line.startswith("From:")
                    else "Date: Tue, 17 Nov 2026 08:00:00 +0530"
                    if line.startswith("Date:")
                    else line
                    for line in raw.splitlines()
                )
            (self.mailbox / "messages" / f"{name}.eml").write_text(raw, "utf-8")

    def copies(self, source: str, count: int) -> list[str]:
        """``count`` copies of one email, each with its own id, all inside the window."""
        names = []
        for n in range(count):
            name = f"copy{n:03d}"
            raw = (FIXTURES / "eml" / f"{source}.eml").read_bytes().decode()
            lines = [
                f"Date: Tue, 17 Nov 2026 {5 + n % 5:02d}:{n % 60:02d}:00 +0530"
                if line.startswith("Date:")
                else line
                for line in raw.splitlines()
            ]
            (self.mailbox / "messages" / f"{name}.eml").write_text("\n".join(lines), "utf-8")
            names.append(name)
        return names

    async def check(self, trigger: str = "button") -> UUID:
        started = await self.runs.start(trigger=trigger, now=self.clock.now())
        await self.run_started(started.search_run_id)
        return started.search_run_id

    async def run_started(self, search_run_id: UUID) -> None:
        """What the worker does: the run goes running, the workflow runs, the run is done."""
        workflow_id = await self._workflow_id(search_run_id)
        async with self.sessions() as session:
            await RunsRepo(session).transition(workflow_id, RunStatus.running)
            await session.commit()
        await run_check(self.deps, {"run_id": str(workflow_id)})
        async with self.sessions() as session:
            await RunsRepo(session).transition(workflow_id, RunStatus.done)
            await session.commit()

    async def _workflow_id(self, search_run_id: UUID) -> UUID:
        async with self.sessions() as session:
            run = await session.get(SearchRunRow, search_run_id)
            assert run is not None
            return run.workflow_run_id


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> Env:
    mailbox = tmp_path / "gmail"
    (mailbox / "messages").mkdir(parents=True)
    (mailbox / "profile.json").write_text(
        json.dumps({"address": "jobseeker@example.invalid"}), "utf-8"
    )
    gmail = WatchedGmail(mailbox)
    clock = FakeClock(NOW)
    events: list[tuple[str, dict[str, Any]]] = []
    queued: list[UUID] = []
    ended: list[str] = []

    async def publish(name: str, data: dict[str, Any]) -> None:
        events.append((name, data))

    async def enqueue(run_id: UUID) -> None:
        queued.append(run_id)

    async def access_ended(message: str) -> None:
        ended.append(message)

    runs = SqlCheckRuns(sessions, enqueue)
    deps = CheckDeps(
        sessions=sessions,
        reader=gmail,
        sink=SqlAlertSink(sessions, {}, ()),
        runs=runs,
        clock=clock,
        publish=publish,
        on_access_ended=access_ended,
    )
    await seed_mail_senders(sessions, SEED)
    async with sessions() as session:
        await ConnectionRepo(session).connect("jobseeker@example.invalid", NOW)
        rule_sets = RuleSetsRepo(session)
        await rule_sets.approve((await rule_sets.propose({}, {})).id)
        await session.commit()
    return Env(sessions, gmail, deps, runs, clock, mailbox, events, queued, ended)


async def set_rules(env: Env, rules: SearchRules) -> None:
    async with env.sessions() as session:
        rule_sets = RuleSetsRepo(session)
        await rule_sets.approve((await rule_sets.propose(rules_to_dict(rules), {})).id)
        await session.commit()


async def count(env: Env, model: Any) -> int:
    async with env.sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def the_check(env: Env, search_run_id: UUID) -> MailCheckRow:
    async with env.sessions() as session:
        return (
            await session.scalars(
                select(MailCheckRow).where(MailCheckRow.search_run_id == search_run_id)
            )
        ).one()


async def the_run(env: Env, search_run_id: UUID) -> SearchRunRow:
    async with env.sessions() as session:
        run = await session.get(SearchRunRow, search_run_id)
        assert run is not None
        return run


async def test_US2_AS1_jobs_added_with_site_link_date(env: Env) -> None:
    env.add("linkedin-01", "naukri-01")

    run_id = await env.check()

    async with env.sessions() as session:
        jobs = (await session.scalars(select(JobRow))).all()
        sources = (await session.scalars(select(JobSourceRow))).all()
        sightings = (await session.scalars(select(AlertSightingRow))).all()
    assert len(jobs) == 3 + 6  # linkedin-01 has 3 jobs, naukri-01 has 6
    assert {j.state for j in jobs} == {"explore"}
    assert {s.kind for s in sources} == {"email_alert"}
    assert {s.site for s in sightings} == {"linkedin", "naukri"}
    assert all(s.link.startswith("https://") and s.alert_date.year == 2026 for s in sightings)
    check = await the_check(env, run_id)
    assert (check.emails_listed, check.emails_skipped, check.emails_read, check.ended) == (
        2,
        0,
        2,
        "finished",
    )
    run = await the_run(env, run_id)
    assert (run.mode, run.outcome, run.added, run.jobs_found) == ("mail_alerts", "finished", 9, 9)
    assert (
        "search.finished",
        {"search_run_id": str(run_id), "outcome": "finished", "stop_message": None},
    ) in env.events


async def test_FR009_the_query_names_only_enabled_senders_and_the_window(env: Env) -> None:
    env.add("linkedin-01")
    async with env.sessions() as session:
        await session.execute(
            text("UPDATE app.mail_senders SET enabled = false WHERE site = 'naukri'")
        )
        await session.commit()

    await env.check()

    (query,) = env.gmail.queries
    assert "naukri.com" not in query
    assert "jobalerts-noreply@linkedin.com" in query
    assert query.endswith(f"after:{int((NOW - timedelta(hours=24)).timestamp())}")


async def test_US2_AS2_second_check_reads_nothing_new(env: Env) -> None:
    env.add("linkedin-01", "naukri-01")
    await env.check()
    env.gmail.fetched.clear()

    run_id = await env.check()

    assert env.gmail.fetched == []  # no email is opened twice (FR-011)
    check = await the_check(env, run_id)
    assert (check.emails_listed, check.emails_skipped, check.emails_read) == (2, 2, 0)
    assert await count(env, JobRow) == 9
    assert await count(env, MailReadMessageRow) == 2


async def test_US2_AS4_rules_leave_out_with_reason_restorable(env: Env) -> None:
    env.add("indeed-01")
    await set_rules(env, SearchRules(title_words=(RuleItem("python", "user"),)))

    run_id = await env.check()

    async with env.sessions() as session:
        states = {j.title: j.state for j in (await session.scalars(select(JobRow))).all()}
        reasons = (
            await session.scalars(
                select(RelevanceDecisionRow.reason).where(RelevanceDecisionRow.outcome == "skipped")
            )
        ).all()
    assert states["Python Developer"] == "explore"
    assert states["QA Automation Engineer"] == "skipped"  # restorable on the summary
    assert reasons
    assert all("none of your roles" in r for r in reasons)
    run = await the_run(env, run_id)
    assert (run.jobs_found, run.skipped_by_rules, run.added) == (3, 2, 1)


async def test_FR018_not_sent_to_relevance_ai_marked_not_checked(env: Env) -> None:
    env.add("linkedin-01")

    await env.check()

    async with env.sessions() as session:
        decisions = (await session.scalars(select(RelevanceDecisionRow))).all()
    assert {(d.decided_by, d.reason) for d in decisions} == {
        ("rules_only_fallback", "Not checked by AI: no description yet")
    }


async def test_FR018a_unlisted_company_shown_and_not_created(env: Env) -> None:
    env.add("linkedin-01")
    before = await count(env, CompanyRow)

    await env.check()

    assert await count(env, JobRow) == 3  # shown ...
    assert await count(env, CompanyRow) == before  # ... and no company is made from an email
    async with env.sessions() as session:
        assert {j.company_id for j in (await session.scalars(select(JobRow))).all()} == {None}


async def test_US2_AS6_instructions_ignored_signal_shown(env: Env) -> None:
    env.add("injection-01", "injection-02")
    env.clock.advance(timedelta(days=-0))
    # these two are older than a day, so read them with a window that reaches them
    env.clock._now = datetime(2026, 10, 22, 12, 0, tzinfo=IST)
    env.deps.clock._now = env.clock._now

    await env.check()

    async with env.sessions() as session:
        jobs = (await session.scalars(select(JobRow))).all()
        messages = (await session.scalars(select(MailReadMessageRow))).all()
    assert len(jobs) == 8  # both emails list the same 8 postings; the instructions are no job
    assert all(j.injection_flags for j in jobs)
    assert {f["location"] for j in jobs for f in j.injection_flags} == {"email"}
    assert all(m.injection_signals for m in messages)
    assert not any("ignore" in j.title.lower() for j in jobs)


async def test_FR016_no_body_stored(env: Env) -> None:
    env.add("linkedin-01", "naukri-01", "indeed-01")
    await env.check()

    async with env.sessions() as session:
        stored = (
            (
                await session.execute(
                    text(
                        "SELECT row_to_json(m)::text FROM app.mail_read_messages m "
                        "UNION ALL SELECT row_to_json(s)::text FROM app.alert_sightings s "
                        "UNION ALL SELECT row_to_json(c)::text FROM app.mail_checks c"
                    )
                )
            )
            .scalars()
            .all()
        )
    blob = " ".join(stored).lower()
    for body_text in (
        "be an early applicant",
        "unsubscribe",
        "manage alerts",
        "recommended for you",
    ):
        assert body_text not in blob
    assert "subject" not in blob


async def test_FR017_unreadable_email_counted_not_failed(env: Env) -> None:
    env.add("linkedin-01")
    env.add(
        "unknown-01", as_sender="naukrialerts@naukri.com"
    )  # a built-in sender, a layout no reader knows

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert (check.emails_listed, check.emails_read, check.emails_unreadable) == (2, 1, 1)
    assert check.ended == "finished"  # one odd email never fails the check
    assert (
        check.emails_skipped + check.emails_read + check.emails_unreadable
    ) == check.emails_listed
    async with env.sessions() as session:
        outcomes = {
            m.provider_message_id: m.outcome
            for m in (await session.scalars(select(MailReadMessageRow))).all()
        }
    assert outcomes == {"linkedin-01": "read", "unknown-01": "unreadable"}
    assert (await the_run(env, run_id)).outcome == "finished"


async def test_FR017_an_email_from_an_added_sender_waits_for_the_ai(env: Env) -> None:
    env.add("unknown-01", as_sender="weekly@digest1.example.invalid")
    async with env.sessions() as session:
        from hiretitan.mail.infra.repos import SendersRepo

        await SendersRepo(session).add_custom("weekly@digest1.example.invalid")
        await session.commit()

    run_id = await env.check()
    again = await env.check()

    async with env.sessions() as session:
        (message,) = (await session.scalars(select(MailReadMessageRow))).all()
    assert message.outcome == "needs_ai"
    assert (await the_check(env, run_id)).emails_unreadable == 1
    assert (await the_check(env, again)).emails_skipped == 0  # read again next time (US3 AS6)


async def test_US2_AS7_stop_keeps_jobs_read(env: Env) -> None:
    names = env.copies("linkedin-01", 45)

    async def stop_after_the_first_batch(name: str, data: dict[str, Any]) -> None:
        env.events.append((name, data))
        if name == "search.batch_done":
            async with env.sessions() as session:
                await SearchRunsRepo(session).request_stop(UUID(data["search_run_id"]))
                await session.commit()

    env.deps = CheckDeps(**{**env.deps.__dict__, "publish": stop_after_the_first_batch})

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert check.ended == "stopped"
    assert (check.emails_listed, check.emails_read) == (45, 20)  # the batch in hand was kept
    assert await count(env, MailReadMessageRow) == 20
    assert await count(env, JobRow) == 3  # the jobs of those emails are in Explore
    assert (await the_run(env, run_id)).outcome == "stopped_by_user"
    assert len(names) == 45


async def test_FR012_at_most_200_messages_and_more_remaining_says_so(env: Env) -> None:
    env.copies("linkedin-01", 230)

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert (check.emails_listed, check.more_remaining) == (200, True)
    assert check.emails_read == 200


async def test_FR005_access_ended_mid_check(env: Env) -> None:
    env.add("linkedin-01", "naukri-01", "indeed-01")
    env.gmail.fail_on = {2: MailAccessEndedError("Gmail access has ended.")}

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert check.ended == "access_ended"
    run = await the_run(env, run_id)
    assert run.outcome == "failed"
    assert run.stop_message == "Gmail access has ended."
    assert env.access_ended == ["Gmail access has ended."]
    assert await count(env, MailReadMessageRow) == 1  # the email read before it ended is kept


async def test_FR005_gmail_not_answering_ends_the_check_quietly(env: Env) -> None:
    env.add("linkedin-01", "naukri-01")
    env.gmail.fail_on = {1: MailUnavailableError("down")}

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert check.ended == "gmail_unavailable"
    assert (await the_run(env, run_id)).outcome == "failed"
    assert env.access_ended == []  # an outage is not the end of the person's access


async def test_R13_a_message_deleted_since_it_was_listed_is_counted(env: Env) -> None:
    env.add("linkedin-01", "naukri-01")
    env.gmail.fail_on = {1: MailMessageNotFoundError("gone")}

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert (check.emails_read, check.emails_unreadable, check.ended) == (1, 1, "finished")


async def test_FR021_no_enabled_sender_means_nothing_to_ask_gmail(env: Env) -> None:
    async with env.sessions() as session:
        await session.execute(text("UPDATE app.mail_senders SET enabled = false"))
        await session.commit()

    run_id = await env.check()

    assert env.gmail.queries == []
    check = await the_check(env, run_id)
    assert (check.emails_listed, check.ended) == (0, "finished")


async def test_US2_AS1_a_check_with_nothing_new_still_finishes(env: Env) -> None:
    run_id = await env.check()  # an empty mailbox

    check = await the_check(env, run_id)
    assert (check.emails_listed, check.ended) == (0, "finished")
    assert (await the_run(env, run_id)).outcome == "finished"


async def test_edge_a_stop_set_before_reading_ends_before_the_first_email(env: Env) -> None:
    env.add("linkedin-01")
    started = await env.runs.start(trigger="button", now=NOW)
    async with env.sessions() as session:
        await SearchRunsRepo(session).request_stop(started.search_run_id)
        await session.commit()

    await env.run_started(started.search_run_id)

    assert env.gmail.fetched == []
    assert (await the_check(env, started.search_run_id)).ended == "stopped"


async def test_edge_disconnect_during_check_stops(env: Env) -> None:
    import asyncio

    from hiretitan.mail_wiring import make_stop_check

    env.add("linkedin-01")
    started = await env.runs.start(trigger="button", now=NOW)
    stopper = asyncio.create_task(make_stop_check(env.sessions, wait_seconds=10)())
    await asyncio.sleep(0.3)  # Disconnect has asked the check to stop and is waiting

    await env.run_started(started.search_run_id)  # the worker sees the flag and ends the check
    await asyncio.wait_for(stopper, timeout=5)  # ... and only then does Disconnect go on

    assert (await the_check(env, started.search_run_id)).ended == "stopped"
    assert (await the_run(env, started.search_run_id)).outcome == "stopped_by_user"


async def test_edge_nothing_to_stop_when_no_mail_check_runs(env: Env) -> None:
    from hiretitan.mail_wiring import make_stop_check

    await make_stop_check(env.sessions, wait_seconds=1)()  # returns at once, no error


async def test_SEC_the_same_id_on_two_list_pages_is_read_once_and_the_counts_add_up(
    env: Env,
) -> None:
    env.add("linkedin-01", "naukri-01")
    env.gmail.pages = [
        MessagePage(["linkedin-01", "naukri-01"], "next"),
        MessagePage(["naukri-01"], None),  # mail that arrived meanwhile shifted the page
    ]

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert (check.emails_listed, check.emails_read, check.ended) == (2, 2, "finished")
    assert env.gmail.fetched == ["linkedin-01", "naukri-01"]


async def test_SEC_an_endless_list_ends(env: Env) -> None:
    env.gmail.pages = [MessagePage([], "same-token") for _ in range(50)]

    run_id = await env.check()

    assert len(env.gmail.queries) <= 5  # a page cap, not a loop
    assert (await the_check(env, run_id)).ended == "finished"


async def test_SEC_an_unexpected_error_ends_the_check_as_failed_and_frees_the_next(
    env: Env,
) -> None:
    env.add("linkedin-01")

    class Broken:
        async def store(self, **_: object) -> object:
            raise RuntimeError("a database constraint failed")

    env.deps = CheckDeps(**{**env.deps.__dict__, "sink": Broken()})

    run_id = await env.check()

    check = await the_check(env, run_id)
    run = await the_run(env, run_id)
    assert check.ended == "failed"
    assert (run.outcome, run.finished_at is not None) == ("failed", True)  # never left "running"
    # the next check can start: nothing is stuck active
    env.deps = CheckDeps(**{**env.deps.__dict__, "sink": SqlAlertSink(env.sessions, {}, ())})
    assert (await the_check(env, await env.check())).ended == "finished"


async def test_SEC_one_email_that_breaks_the_reader_is_unreadable_not_a_failed_check(
    env: Env,
) -> None:
    env.add("linkedin-01", "naukri-01")
    env.gmail.fail_on = {1: ValueError("a message nobody can read")}

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert (check.emails_read, check.emails_unreadable, check.ended) == (1, 1, "finished")


async def test_SEC_an_email_with_no_usable_sender_is_unreadable_and_recorded(env: Env) -> None:
    raw = (FIXTURES / "eml" / "linkedin-01.eml").read_text("utf-8").splitlines()
    body = [line for line in raw if not line.startswith("From:")]
    (env.mailbox / "messages" / "nofrom.eml").write_text("\n".join(body), "utf-8")
    env.gmail.pages = [MessagePage(["nofrom"], None)]

    run_id = await env.check()

    async with env.sessions() as session:
        (message,) = (await session.scalars(select(MailReadMessageRow))).all()
    assert (message.outcome, message.sender) == ("unreadable", "unknown@invalid")
    assert (await the_check(env, run_id)).ended == "finished"


async def test_SEC_a_display_name_that_looks_like_a_listed_address_is_not_trusted(
    env: Env,
) -> None:
    raw = (
        (FIXTURES / "eml" / "linkedin-01.eml")
        .read_text("utf-8")
        .replace(
            "From: LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
            'From: "jobalerts-noreply@linkedin.com" <someone@evil.example.invalid>',
        )
    )
    (env.mailbox / "messages" / "spoof.eml").write_text(raw, "utf-8")
    env.gmail.pages = [MessagePage(["spoof"], None)]

    await env.check()

    assert await count(env, JobRow) == 0  # no fake jobs from a borrowed name


async def test_SEC_a_stop_during_the_last_batch_is_still_a_stop(env: Env) -> None:
    env.add("linkedin-01", "naukri-01", "indeed-01")

    async def stop_at_the_second_fetch(number: int) -> None:
        if number == 2:
            async with env.sessions() as session:
                run = (await session.scalars(select(SearchRunRow))).one()
                await SearchRunsRepo(session).request_stop(run.id)
                await session.commit()

    env.gmail.on_fetch = stop_at_the_second_fetch

    run_id = await env.check()

    assert (await the_check(env, run_id)).ended == "stopped"
    assert (await the_run(env, run_id)).outcome == "stopped_by_user"
    assert await count(env, MailReadMessageRow) == 3  # what was read is kept


async def test_FR016_the_text_of_an_instruction_is_not_kept(env: Env) -> None:
    env.add("injection-01", "injection-02")
    env.clock._now = datetime(2026, 10, 22, 12, 0, tzinfo=IST)
    env.deps.clock._now = env.clock._now

    await env.check()

    async with env.sessions() as session:
        messages = (await session.scalars(select(MailReadMessageRow))).all()
        jobs = (await session.scalars(select(JobRow))).all()
    flags = [f for m in messages for f in m.injection_signals] + [
        f for j in jobs for f in j.injection_flags
    ]
    assert flags
    assert {f["excerpt"] for f in flags} == {""}  # which rule and where, never the email's words


async def test_edge_nothing_is_stored_after_disconnect(env: Env) -> None:
    env.add("linkedin-01")
    started = await env.runs.start(trigger="button", now=NOW)
    async with env.sessions() as session:
        await ConnectionRepo(session).remove()  # Disconnect happened while the check was queued
        await session.commit()

    await env.run_started(started.search_run_id)

    assert await count(env, MailReadMessageRow) == 0
    assert await count(env, JobRow) == 0


async def test_edge_a_run_deleted_by_delete_all_ends_quietly(env: Env) -> None:
    env.add("linkedin-01")
    started = await env.runs.start(trigger="button", now=NOW)
    async with env.sessions() as session:
        await session.execute(text("DELETE FROM app.search_runs"))
        await session.commit()

    result = await env.deps.sink.store(
        search_run_id=started.search_run_id,
        mail_check_id=started.mail_check_id,
        batch_no=1,
        emails=[],
        now=NOW,
    )

    assert result.found == 0  # no crash on a run that no longer exists


async def test_SEC_the_runner_giving_up_ends_the_check_as_failed(env: Env) -> None:
    from hiretitan.mail.workflow.check import mail_check_workflow

    started = await env.runs.start(trigger="button", now=NOW)
    workflow_id = await env._workflow_id(started.search_run_id)
    async with env.sessions() as session:
        run = await RunsRepo(session).get(workflow_id)
    assert run is not None
    on_failed = mail_check_workflow(env.deps).on_failed
    assert on_failed is not None

    await on_failed(run)

    assert (await the_check(env, started.search_run_id)).ended == "failed"
    finished = await the_run(env, started.search_run_id)
    assert (finished.outcome, finished.finished_at is not None) == ("failed", True)
