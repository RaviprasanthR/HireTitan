"""No repeats (T034): US3 AS1-AS6 and SC-003, through the whole mail check.

Fake Gmail over the synthetic fixtures, real PostgreSQL. A job the person already has (from a
searched board, the pipeline, or deleted) is made directly with the repositories.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from tests.workflow.mail.test_check import NOW, Env, count, the_run

from hiretitan.mail.infra.models import MailReadMessageRow
from hiretitan.mail_wiring import mail_run_details
from hiretitan.search.infra.models import (
    AlertSightingRow,
    JobRow,
    JobSourceRow,
    PossibleDuplicateRow,
    RelevanceDecisionRow,
)
from hiretitan.search.infra.repos import DuplicatesRepo, JobsRepo

LINKEDIN = "https://www.linkedin.com/jobs/view/3978721496"  # linkedin-01's Data Engineer
GRANITE = "Granite Insurance Tech"  # cutshort-01's Data Engineer, Gurugram


async def seed_job(env: Env, **fields: object) -> UUID:
    values: dict[str, object] = {
        "company_id": None,
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "description": "",
        "state": "explore",
    } | fields
    async with env.sessions() as session:
        job = await JobsRepo(session).add(**values)
        await session.commit()
        return job.id


def retrack(env: Env, name: str, old: str, new: str) -> None:
    """Change the tracking part of every link in one fixture copy; the postings stay the same."""
    path: Path = env.mailbox / "messages" / f"{name}.eml"
    path.write_text(path.read_text("utf-8").replace(old, new), "utf-8")


async def test_US3_AS1_same_link_in_several_alerts_one_job_all_sightings(env: Env) -> None:
    names = env.copies("linkedin-01", 3)
    retrack(env, names[1], "refId=x102", "refId=other")
    retrack(env, names[2], "trackingId=2894488586", "trackingId=1")

    await env.check()

    assert await count(env, JobRow) == 3  # linkedin-01 has three postings
    assert await count(env, AlertSightingRow) == 9  # each seen in all three emails
    async with env.sessions() as session:
        per_job = (
            await session.execute(
                select(func.count()).select_from(AlertSightingRow).group_by(AlertSightingRow.job_id)
            )
        ).scalars()
        assert sorted(per_job) == [3, 3, 3]


async def test_US3_AS2_alert_matches_searched_job_adds_source(env: Env) -> None:
    existing = await seed_job(
        env,
        company_name="Aspen Robotics",
        title="Data Engineer",
        canonical_url=LINKEDIN,
        ats_vendor="greenhouse",
        requisition_id="gh-1",
    )
    env.add("linkedin-01")

    await env.check()

    assert await count(env, JobRow) == 3  # the two other postings are new, this one is not
    async with env.sessions() as session:
        kinds = (
            await session.scalars(select(JobSourceRow.kind).where(JobSourceRow.job_id == existing))
        ).all()
        sightings = await session.scalar(
            select(func.count())
            .select_from(AlertSightingRow)
            .where(AlertSightingRow.job_id == existing)
        )
    assert kinds == ["email_alert"]  # the source is added next to the one it already had
    assert sightings == 1


async def test_US3_AS3_near_match_other_site_is_candidate_not_merged(env: Env) -> None:
    other = await seed_job(env, company_name=GRANITE, title="Data Engineer ", city="Gurugram")
    env.add("cutshort-01")

    await env.check()

    assert await count(env, JobRow) == 3  # nothing is merged on a guess
    async with env.sessions() as session:
        pairs = (await session.scalars(select(PossibleDuplicateRow))).all()
    assert len(pairs) == 1
    assert other in (pairs[0].job_a_id, pairs[0].job_b_id)
    assert pairs[0].status == "open"


async def test_US3_AS4_pipeline_job_not_listed_again_summary_says_which(env: Env) -> None:
    await seed_job(
        env,
        company_name=GRANITE,
        title="Data Engineer",
        city="Gurugram",
        state="applied",
        applied_on=NOW.date(),
    )
    env.add("cutshort-01")

    run_id = await env.check()

    async with env.sessions() as session:
        decisions = (
            await session.scalars(
                select(RelevanceDecisionRow).where(
                    RelevanceDecisionRow.rule_key == "already_in_pipeline"
                )
            )
        ).all()
        mail = await mail_run_details(session, run_id)
    assert len(decisions) == 1
    assert "Already in your pipeline as Data Engineer" in decisions[0].reason
    assert mail is not None
    assert [(p.title, p.company) for p in mail.already_in_pipeline] == [("Data Engineer", GRANITE)]
    run = await the_run(env, run_id)
    assert run.jobs_found == 2  # both postings are counted; one of them is left out


async def test_US3_AS5_deleted_job_stays_deleted(env: Env) -> None:
    env.add("linkedin-01")
    await env.check()
    async with env.sessions() as session:
        job = (await session.scalars(select(JobRow).where(JobRow.canonical_url == LINKEDIN))).one()
        job.state = "deleted"
        await session.commit()
    retrack(env, env.copies("linkedin-01", 1)[0], "refId=x102", "refId=again")

    await env.check()

    async with env.sessions() as session:
        jobs = (await session.scalars(select(JobRow))).all()
    assert len(jobs) == 3
    assert {j.state for j in jobs if j.canonical_url == LINKEDIN} == {"deleted"}


async def test_US3_AS5_not_the_same_pair_not_proposed_again(env: Env) -> None:
    other = await seed_job(env, company_name=GRANITE, title="Data Engineer ", city="Gurugram")
    env.add("cutshort-01")
    await env.check()
    async with env.sessions() as session:
        pair = (await session.scalars(select(PossibleDuplicateRow))).one()
        await DuplicatesRepo(session).set_status(
            pair.id, "dismissed", decided_at=datetime.now(NOW.tzinfo)
        )
        await session.commit()
    # the same posting again (another email, another tracking): exact match, no new pair
    retrack(env, env.copies("cutshort-01", 1)[0], "ref=email", "ref=again")

    await env.check()

    async with env.sessions() as session:
        pairs = (await session.scalars(select(PossibleDuplicateRow))).all()
    assert [p.status for p in pairs] == ["dismissed"]
    assert await count(env, JobRow) == 3

    # a *different* posting of the same company, place and title is a new question to the person,
    # but the answered pair itself is never asked again
    retrack(env, "copy000", "6sF7bQzE", "NEWID123")
    await env.check()
    async with env.sessions() as session:
        pairs = (await session.scalars(select(PossibleDuplicateRow))).all()
    assert sum(1 for p in pairs if p.status == "dismissed") == 1
    assert sum(1 for p in pairs if {p.job_a_id, p.job_b_id} == {pair.job_a_id, pair.job_b_id}) == 1
    assert other in {pair.job_a_id, pair.job_b_id}


async def test_US3_AS6_email_never_read_twice(env: Env) -> None:
    env.add("linkedin-01", "cutshort-01")
    await env.check()
    env.gmail.fetched.clear()

    await env.check()
    await env.check("daily")

    assert env.gmail.fetched == []
    assert await count(env, MailReadMessageRow) == 2
    assert await count(env, AlertSightingRow) == 5  # no sighting is added by a second look


async def test_SC003_shared_link_or_posting_id_always_one_job(env: Env) -> None:
    # one posting, four ways to meet it: the same email twice with other tracking, the address
    # with a trailing slash, and the posting number with another address form
    names = env.copies("linkedin-01", 4)
    retrack(env, names[1], "?trackingId=", "/?trackingId=")
    retrack(env, names[2], "refId=x102", "refId=a&utm_source=b")
    retrack(env, names[3], "/comm/jobs/view/", "/jobs/view/")

    await env.check()

    async with env.sessions() as session:
        keys = (await session.execute(select(JobRow.ats_vendor, JobRow.requisition_id))).all()
    assert len(keys) == len(set(keys)) == 3


async def test_US3_AS4_same_link_as_a_pipeline_job_is_listed_as_already_there(env: Env) -> None:
    applied = await seed_job(
        env,
        company_name="Aspen Robotics",
        title="Data Engineer",
        canonical_url=LINKEDIN,
        state="applied",
        applied_on=NOW.date(),
    )
    env.add("linkedin-01")

    run_id = await env.check()

    async with env.sessions() as session:
        mail = await mail_run_details(session, run_id)
        job = await session.get(JobRow, applied)
    assert mail is not None
    assert [p.job_id for p in mail.already_in_pipeline] == [applied]
    assert job is not None
    assert job.state == "applied"
    run = await the_run(env, run_id)
    assert run.jobs_found == 3  # found = new (2) + already in pipeline (1)
    assert run.added == 2


async def test_US3_AS5_a_deleted_job_is_left_exactly_as_it_was(env: Env) -> None:
    deleted = await seed_job(
        env,
        company_name="Aspen Robotics",
        title="Data Engineer",
        canonical_url=LINKEDIN,
        state="deleted",
        listed=False,
    )
    env.add("linkedin-01")

    await env.check()

    async with env.sessions() as session:
        job = await session.get(JobRow, deleted)
        sources = await session.scalar(
            select(func.count()).select_from(JobSourceRow).where(JobSourceRow.job_id == deleted)
        )
    assert job is not None
    assert (job.state, job.listed, job.last_seen_at) == ("deleted", False, NOW)
    assert sources == 0
    assert await count(env, JobRow) == 3  # it is not added a second time
