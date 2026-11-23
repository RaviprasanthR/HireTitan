"""Starting a check and reading its results over the API (T026): FR-019, FR-020, FR-021, US2.

The check itself is tested in ``tests/workflow/mail``; here the HTTP side: starting one, the
``mail`` member of a search run, the Email-alerts filter and the job's alert sources.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.mail_env import make_run

from hiretitan.api_main import create_app
from hiretitan.mail.api.checks import MailChecksApiDeps, create_checks_router
from hiretitan.mail.infra.models import MailReadMessageRow
from hiretitan.mail.infra.repos import ConnectionRepo, MailChecksRepo
from hiretitan.mail_wiring import SqlCheckRuns, mail_run_details
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.api.runs import SearchRunsApiDeps, create_search_runs_router
from hiretitan.search.application.synonyms_seed import load_title_synonyms
from hiretitan.search.infra.models import AlertSightingRow
from hiretitan.search.infra.repos import JobsRepo, RuleSetsRepo
from hiretitan.search_wiring import ProfileAndPreferencesSource

SEED = Path(__file__).resolve().parents[3] / "seed" / "title_synonyms.yaml"
NOW = datetime(2026, 11, 18, 9, tzinfo=UTC)


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Setup:
    def gate(self, _session: AsyncSession) -> Setup:
        return self

    async def setup_complete(self) -> bool:
        return True


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    queue: Queue


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    queue, clock = Queue(), FakeClock(NOW)

    async def enqueue(run_id: UUID) -> None:
        await queue.enqueue(run_id)

    runs = SqlCheckRuns(sessions, enqueue)
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_checks_router(MailChecksApiDeps(runs=runs, clock=clock)),
            create_search_runs_router(
                SearchRunsApiDeps(
                    sessions=sessions,
                    queue=queue,
                    clock=clock,
                    source=ProfileAndPreferencesSource,
                    synonyms=load_title_synonyms(SEED),
                    setup_gate=Setup().gate,
                    mail_details=mail_run_details,
                )
            ),
            create_search_jobs_router(
                SearchJobsApiDeps(
                    sessions=sessions,
                    queue=queue,
                    clock=clock,
                    resume_lookup=lambda _s: None,  # type: ignore[arg-type,return-value]
                    job_cleanups=(),
                )
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, queue)


async def connected(env: Env, state: str = "connected") -> None:
    async with env.sessions() as session:
        await ConnectionRepo(session).connect("jobseeker@example.invalid", NOW)
        if state != "connected":
            await ConnectionRepo(session).set_state(state, "Gmail access has ended.")
        await session.commit()


async def approved_rules(env: Env) -> None:
    async with env.sessions() as session:
        rules = RuleSetsRepo(session)
        await rules.approve((await rules.propose({}, {})).id)
        await session.commit()


async def test_FR021_post_check_202(env: Env) -> None:
    await connected(env)
    await approved_rules(env)

    response = await env.client.post("/api/v1/mail/checks")

    assert response.status_code == 202
    run_id = UUID(response.json()["search_run_id"])
    assert len(env.queue.enqueued) == 1  # handed to the worker
    run = (await env.client.get(f"/api/v1/search/runs/{run_id}")).json()
    assert run["mode"] == "mail_alerts"
    assert run["mail"] == {
        "trigger": "button",
        "window_start": (NOW - timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
        "emails_listed": 0,
        "emails_skipped": 0,
        "emails_read": 0,
        "emails_unreadable": 0,
        "more_remaining": False,
        "ended": None,
        "unreadable": [],
        "already_in_pipeline": [],
    }


async def test_check_not_connected_409(env: Env) -> None:
    await approved_rules(env)

    response = await env.client.post("/api/v1/mail/checks")

    assert response.status_code == 409
    assert response.json()["reason"] == "not_connected"
    assert env.queue.enqueued == []


async def test_check_needs_reconnect_409(env: Env) -> None:
    await connected(env, "needs_reconnect")
    await approved_rules(env)

    response = await env.client.post("/api/v1/mail/checks")

    assert (response.status_code, response.json()["reason"]) == (409, "needs_reconnect")


async def test_check_without_approved_rules_409(env: Env) -> None:
    await connected(env)

    response = await env.client.post("/api/v1/mail/checks")

    assert (response.status_code, response.json()["reason"]) == (409, "rules_not_approved")


async def test_check_while_search_running_409(env: Env) -> None:
    await connected(env)
    async with env.sessions() as session:
        await make_run(session, mode="rules_only")  # a search that is queued: one at a time
        await session.commit()

    response = await env.client.post("/api/v1/mail/checks")

    assert (response.status_code, response.json()["reason"]) == (409, "search_running")
    assert env.queue.enqueued == []


async def test_runs_include_mail_member_for_mail_runs_only(env: Env) -> None:
    async with env.sessions() as session:
        company_run = await make_run(session, mode="rules_only")
        mail_run = await make_run(session, mode="mail_alerts")
        check = await MailChecksRepo(session).create(mail_run, "daily", NOW - timedelta(hours=24))
        await MailChecksRepo(session).finish(
            check.id,
            listed=3,
            skipped=1,
            read=1,
            unreadable=1,
            more_remaining=False,
            ended="finished",
        )
        session.add(
            MailReadMessageRow(
                provider_message_id="18c0ffee00000001",
                sender="naukrialerts@naukri.com",
                received_at=NOW,
                purpose="job_alert",
                outcome="unreadable",
                reader=None,
                jobs_found=0,
                injection_signals=[],
                mail_check_id=check.id,
                read_at=NOW,
            )
        )
        await session.commit()

    company = (await env.client.get(f"/api/v1/search/runs/{company_run}")).json()
    mail = (await env.client.get(f"/api/v1/search/runs/{mail_run}")).json()
    history = (await env.client.get("/api/v1/search/runs")).json()["items"]

    assert company["mail"] is None
    assert mail["mail"]["emails_listed"] == 3
    assert mail["mail"]["ended"] == "finished"
    assert mail["mail"]["unreadable"] == [
        {
            "sender": "naukrialerts@naukri.com",
            "received_at": NOW.isoformat().replace("+00:00", "Z"),
            "why": "unreadable",
        }
    ]
    assert {item["id"]: item["mail"] is not None for item in history} == {
        str(company_run): False,
        str(mail_run): True,
    }


async def add_alert_job(
    env: Env, *, posted_at: datetime | None = None, posting: str = "3978721496"
) -> UUID:
    async with env.sessions() as session:
        job = await JobsRepo(session).add(
            company_id=None,
            company_name="Aspen Robotics",
            title="Data Engineer",
            first_seen_at=NOW,
            last_seen_at=NOW,
            posted_at=posted_at,
            description="",
            state="explore",
            ats_vendor="linkedin",
            requisition_id=posting,
        )
        await JobsRepo(session).add_source(
            job.id,
            kind="email_alert",
            url=f"https://www.linkedin.com/jobs/view/{posting}/",
            seen_at=NOW,
        )
        session.add(
            AlertSightingRow(
                job_id=job.id,
                read_message_id=None,
                site="linkedin",
                link=f"https://www.linkedin.com/comm/jobs/view/{posting}/?trk=1",
                alert_date=NOW - timedelta(hours=5),
                posted_at=posted_at,
            )
        )
        await session.commit()
        return job.id


async def test_FR019_source_filter_email_alert(env: Env) -> None:
    alert = await add_alert_job(env)
    async with env.sessions() as session:
        other = await JobsRepo(session).add(
            company_id=None,
            company_name="Other",
            title="QA",
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="",
            state="explore",
        )
        await JobsRepo(session).add_source(
            other.id, kind="paste", url="https://x.invalid/1", seen_at=NOW
        )
        await session.commit()

    everything = (await env.client.get("/api/v1/jobs")).json()["items"]
    only_alerts = (await env.client.get("/api/v1/jobs?source=email_alert")).json()["items"]

    assert len(everything) == 2
    assert [item["id"] for item in only_alerts] == [str(alert)]


async def test_FR019_job_sources_show_site_and_date(env: Env) -> None:
    job_id = await add_alert_job(env)

    card = (await env.client.get(f"/api/v1/jobs/{job_id}")).json()

    (source,) = card["sources"]
    assert source["kind"] == "email_alert"
    assert source["site"] == "linkedin"
    assert source["alert_date"] == (NOW - timedelta(hours=5)).isoformat().replace("+00:00", "Z")


async def test_FR019_a_source_that_is_not_an_alert_has_no_site_or_date(env: Env) -> None:
    async with env.sessions() as session:
        job = await JobsRepo(session).add(
            company_id=None,
            company_name="Other",
            title="QA",
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="",
            state="explore",
        )
        await JobsRepo(session).add_source(
            job.id, kind="paste", url="https://x.invalid/1", seen_at=NOW
        )
        await session.commit()

    card = (await env.client.get(f"/api/v1/jobs/{job.id}")).json()

    assert card["sources"] == [
        {"kind": "paste", "url": "https://x.invalid/1", "site": None, "alert_date": None}
    ]
    assert card["may_have_closed"] is False


async def test_FR020_may_have_closed_after_30_days(env: Env) -> None:
    old = await add_alert_job(env, posted_at=datetime.now(UTC) - timedelta(days=45))
    fresh_id = await add_alert_job(
        env, posted_at=datetime.now(UTC) - timedelta(days=3), posting="3978721497"
    )
    unknown = await add_alert_job(env, posted_at=None, posting="3978721498")

    flags = {}
    for name, job_id in (("old", old), ("fresh", fresh_id), ("unknown", unknown)):
        flags[name] = (await env.client.get(f"/api/v1/jobs/{job_id}")).json()["may_have_closed"]

    # only a posting date the alert itself gave, more than 30 days back, marks it (FR-020)
    assert flags == {"old": True, "fresh": False, "unknown": False}


async def test_FR020_a_job_not_from_an_alert_is_never_marked(env: Env) -> None:
    async with env.sessions() as session:
        job = await JobsRepo(session).add(
            company_id=None,
            company_name="Other",
            title="QA",
            first_seen_at=NOW,
            last_seen_at=NOW,
            posted_at=datetime.now(UTC) - timedelta(days=90),
            description="",
            state="explore",
        )
        await JobsRepo(session).add_source(
            job.id, kind="company_board", url="https://x.invalid/1", seen_at=NOW
        )
        await session.commit()

    assert (await env.client.get(f"/api/v1/jobs/{job.id}")).json()["may_have_closed"] is False


async def test_US2_AS6_the_email_instruction_signal_is_on_the_job(env: Env) -> None:
    job_id = await add_alert_job(env)
    async with env.sessions() as session:
        await session.execute(
            text("UPDATE app.jobs SET injection_flags = :f ::jsonb WHERE id = :id"),
            {
                "f": (
                    '[{"rule_id": "ignore_previous", "severity": "high",'
                    ' "excerpt": "x", "location": "email"}]'
                ),
                "id": job_id,
            },
        )
        await session.commit()

    card = (await env.client.get(f"/api/v1/jobs/{job_id}")).json()

    assert [f["location"] for f in card["injection_flags"]] == ["email"]


async def read_record(env: Env, message_id: str, received: datetime) -> None:
    async with env.sessions() as session:
        session.add(
            MailReadMessageRow(
                provider_message_id=message_id,
                sender="jobalerts-noreply@linkedin.com",
                received_at=received,
                purpose="job_alert",
                outcome="read",
                reader="linkedin",
                jobs_found=1,
                injection_signals=[],
                read_at=received,
            )
        )
        await session.commit()


async def provider_ids(env: Env) -> set[str]:
    async with env.sessions() as session:
        rows = await session.scalars(text("SELECT provider_message_id FROM app.mail_read_messages"))
        return set(rows)


async def test_FR013e_read_the_last_day_again_forgets_only_the_last_24_hours(env: Env) -> None:
    await connected(env)
    await approved_rules(env)
    await read_record(env, "recent", NOW - timedelta(hours=3))
    await read_record(env, "old", NOW - timedelta(hours=30))

    response = await env.client.post("/api/v1/mail/checks", json={"reread_last_day": True})

    assert response.status_code == 202
    assert len(env.queue.enqueued) == 1
    assert await provider_ids(env) == {"old"}


async def test_FR013e_a_plain_check_forgets_nothing(env: Env) -> None:
    await connected(env)
    await approved_rules(env)
    await read_record(env, "recent", NOW - timedelta(hours=3))

    response = await env.client.post("/api/v1/mail/checks", json={"reread_last_day": False})

    assert response.status_code == 202
    assert await provider_ids(env) == {"recent"}


async def test_FR013e_read_again_while_a_check_runs_forgets_nothing(env: Env) -> None:
    await connected(env)
    await approved_rules(env)
    await read_record(env, "recent", NOW - timedelta(hours=3))
    assert (await env.client.post("/api/v1/mail/checks")).status_code == 202

    response = await env.client.post("/api/v1/mail/checks", json={"reread_last_day": True})

    assert response.status_code == 409
    assert response.json()["reason"] == "search_running"
    assert await provider_ids(env) == {"recent"}


async def test_FR013e_read_again_drops_the_forgotten_emails_sightings(env: Env) -> None:
    # read again, each email adds its sighting anew: the old one must not stay as a second alert
    await connected(env)
    await approved_rules(env)
    await read_record(env, "recent", NOW - timedelta(hours=3))
    async with env.sessions() as session:
        job = await JobsRepo(session).add(
            company_name="Aspen Robotics",
            title="Data Engineer",
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="",
            state="explore",
        )
        message_id = (await session.scalars(text("SELECT id FROM app.mail_read_messages"))).one()
        session.add(
            AlertSightingRow(
                job_id=job.id,
                read_message_id=message_id,
                site="linkedin",
                link="https://www.linkedin.com/comm/jobs/view/1/",
                alert_date=NOW,
            )
        )
        await session.commit()

    response = await env.client.post("/api/v1/mail/checks", json={"reread_last_day": True})

    assert response.status_code == 202
    async with env.sessions() as session:
        left = (await session.scalars(text("SELECT count(*) FROM app.alert_sightings"))).one()
    assert left == 0
