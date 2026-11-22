"""Alert jobs into the search tables (T031): FR-018, FR-018a, FR-019, FR-022, US2 AS1/AS4/AS6.

Real PostgreSQL. The postings are the neutral records the mail module hands over (``AlertPosting``);
the rules, deduplication and the batch writer are the search module's own.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fakes.mail_env import make_run

from hiretitan.mail.infra.models import MailReadMessageRow
from hiretitan.search.application.alerts import (
    NO_COMPANY,
    AlertPosting,
    store_alert_postings,
)
from hiretitan.search.domain.rules import RuleItem, SearchRules
from hiretitan.search.infra.models import (
    AlertSightingRow,
    CompanyRow,
    JobRow,
    JobSourceRow,
    PossibleDuplicateRow,
    RelevanceDecisionRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo
from hiretitan.search.infra.search_store import AlertSearchStore

NOW = datetime(2026, 11, 18, 9, tzinfo=UTC)
ALERT = NOW - timedelta(hours=5)
RULES = SearchRules(title_words=(RuleItem("engineer", "user"),))


def posting(
    title: str = "Data Engineer",
    company: str | None = "Aspen Robotics",
    location: str | None = "Pune",
    posting_id: str = "3978721496",
    site: str = "linkedin",
    message: UUID | None = None,
    signals: list[dict[str, object]] | None = None,
) -> AlertPosting:
    link = f"https://www.linkedin.com/comm/jobs/view/{posting_id}/?trackingId=1&refId=x"
    return AlertPosting(
        title=title,
        company=company,
        location=location,
        link=link,
        clean_link=f"https://www.linkedin.com/jobs/view/{posting_id}/",
        posting_id=posting_id,
        site=site,
        alert_date=ALERT,
        posted_at=None,
        injection_signals=signals or [],
        read_message_id=message,
    )


async def message_row(session: AsyncSession, n: int) -> UUID:
    row = MailReadMessageRow(
        provider_message_id=f"18c0ffee0000000{n}",
        sender="jobalerts-noreply@linkedin.com",
        received_at=ALERT,
        purpose="job_alert",
        outcome="read",
        reader="linkedin",
        jobs_found=1,
        injection_signals=[],
        read_at=NOW,
    )
    session.add(row)
    await session.flush()
    return row.id


async def store(
    session: AsyncSession, run_id: UUID, postings: list[AlertPosting], batch: int = 1
) -> object:
    return await store_alert_postings(
        AlertSearchStore(session),
        search_run_id=run_id,
        batch_no=batch,
        postings=postings,
        rules=RULES,
        synonyms={},
        tech_names=(),
        now=NOW,
    )


async def jobs(session: AsyncSession) -> list[JobRow]:
    return list((await session.scalars(select(JobRow).order_by(JobRow.title))).all())


async def test_US2_AS1_a_new_alert_job_is_added_to_explore_with_site_link_and_date(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session)
    message = await message_row(db_session, 1)

    counts = await store(db_session, run_id, [posting(message=message)])

    (job,) = await jobs(db_session)
    assert (job.title, job.company_name, job.location_text, job.state) == (
        "Data Engineer",
        "Aspen Robotics",
        "Pune",
        "explore",
    )
    assert (job.ats_vendor, job.requisition_id) == ("linkedin", "3978721496")
    assert job.canonical_url == "https://www.linkedin.com/jobs/view/3978721496"  # normalised
    source = (await db_session.scalars(select(JobSourceRow))).one()
    assert (source.kind, source.url, source.search_run_id) == (
        "email_alert",
        "https://www.linkedin.com/jobs/view/3978721496/",
        run_id,
    )
    sighting = (await db_session.scalars(select(AlertSightingRow))).one()
    assert (sighting.job_id, sighting.read_message_id, sighting.site, sighting.alert_date) == (
        job.id,
        message,
        "linkedin",
        ALERT,
    )
    assert sighting.link.startswith("https://www.linkedin.com/comm/jobs/view/3978721496/?tracking")
    assert (counts.new, counts.already_known, counts.left_out) == (1, 0, 0)  # type: ignore[attr-defined]
    run = await db_session.get(SearchRunRow, run_id)
    assert run is not None
    assert (run.jobs_found, run.added, run.not_checked_by_ai) == (1, 1, 1)


async def test_FR018_not_sent_to_relevance_ai_marked_not_checked(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)

    await store(db_session, run_id, [posting()])

    decision = (await db_session.scalars(select(RelevanceDecisionRow))).one()
    assert (decision.outcome, decision.decided_by) == ("shown", "rules_only_fallback")
    assert decision.reason == "Not checked by AI: no description yet"
    assert decision.search_run_id == run_id


async def test_US2_AS4_rules_leave_out_with_reason_restorable(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)

    counts = await store(db_session, run_id, [posting(title="Marketing Manager")])

    (job,) = await jobs(db_session)
    assert job.state == "skipped"  # the state Restore brings back to Explore
    decision = (await db_session.scalars(select(RelevanceDecisionRow))).one()
    assert (decision.outcome, decision.decided_by, decision.rule_key) == (
        "skipped",
        "rule",
        "title_words",
    )
    assert "none of your roles" in decision.reason
    assert (counts.new, counts.left_out) == (0, 1)  # type: ignore[attr-defined]


async def test_FR018a_unlisted_company_shown_and_not_created(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    known = await CompaniesRepo(db_session).add(
        name="Aspen Robotics", origin="user", resolution="verified"
    )

    await store(
        db_session,
        run_id,
        [
            posting(company="Aspen Robotics", posting_id="3900000001"),
            posting(company="Zephyr Media", posting_id="3900000002"),
        ],
    )

    by_company = {j.company_name: j for j in await jobs(db_session)}
    assert by_company["Aspen Robotics"].company_id == known.id  # found by name
    assert by_company["Zephyr Media"].company_id is None  # shown, and no company row is made
    names = set((await db_session.scalars(select(CompanyRow.name))).all())
    assert "Zephyr Media" not in names


async def test_FR013_a_missing_company_and_place_stay_empty(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)

    await store(db_session, run_id, [posting(company=None, location=None)])

    (job,) = await jobs(db_session)
    assert job.company_name == NO_COMPANY
    assert job.company_id is None
    assert (job.location_text, job.city, job.country) == (None, None, None)


async def test_US2_AS6_instructions_ignored_signal_shown(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    signal = {
        "rule_id": "ignore_previous",
        "severity": "high",
        "excerpt": "ignore all previous instructions",
        "location": "hidden",
    }

    await store(db_session, run_id, [posting(signals=[signal])])

    (job,) = await jobs(db_session)
    assert [f["rule_id"] for f in job.injection_flags] == ["ignore_previous"]
    assert {f["location"] for f in job.injection_flags} == {"email"}  # where it was found


async def test_FR022_the_same_posting_in_two_emails_is_one_job_with_two_sightings(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session)
    first, second = await message_row(db_session, 1), await message_row(db_session, 2)
    other_tracking = replace(
        posting(message=second),
        link="https://www.linkedin.com/comm/jobs/view/3978721496/?trk=other",
    )

    counts = await store(db_session, run_id, [posting(message=first), other_tracking])

    assert len(await jobs(db_session)) == 1
    sightings = (await db_session.scalars(select(AlertSightingRow))).all()
    assert {s.read_message_id for s in sightings} == {first, second}
    assert (counts.new, counts.already_known) == (1, 0)  # type: ignore[attr-defined]


async def test_FR022_a_later_check_adds_a_sighting_not_a_job(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    first, second = await message_row(db_session, 1), await message_row(db_session, 2)
    await store(db_session, run_id, [posting(message=first)], batch=1)

    counts = await store(db_session, run_id, [posting(message=second)], batch=2)

    assert len(await jobs(db_session)) == 1
    assert (counts.new, counts.already_known) == (0, 1)  # type: ignore[attr-defined]
    assert await db_session.scalar(select(func.count()).select_from(AlertSightingRow)) == 2
    sources = (await db_session.scalars(select(JobSourceRow))).all()
    assert len(sources) == 1  # the same clean link is not a second source


async def test_FR022_a_job_the_person_deleted_stays_deleted(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    await store(db_session, run_id, [posting()], batch=1)
    (job,) = await jobs(db_session)
    job.state = "deleted"
    await db_session.flush()

    counts = await store(db_session, run_id, [posting()], batch=2)

    (job,) = await jobs(db_session)
    assert job.state == "deleted"
    assert counts.already_known == 1  # type: ignore[attr-defined]


async def test_US3_AS4_pipeline_job_not_listed_again_summary_says_which(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session)
    await JobsRepo(db_session).add(
        company_id=None,
        company_name="Aspen Robotics",
        title="Data Engineer",
        city="Pune",
        first_seen_at=NOW,
        last_seen_at=NOW,
        description="",
        state="applied",
        applied_on=NOW.date(),
    )

    counts = await store(db_session, run_id, [posting(location="Pune")])

    listed = [j for j in await jobs(db_session) if j.state != "applied"]
    assert [j.state for j in listed] == ["skipped"]
    assert counts.already_in_pipeline == 1  # type: ignore[attr-defined]
    assert counts.in_pipeline_titles == ("Data Engineer",)  # type: ignore[attr-defined]
    decision = (
        await db_session.scalars(
            select(RelevanceDecisionRow).where(RelevanceDecisionRow.job_id == listed[0].id)
        )
    ).one()
    assert decision.rule_key == "already_in_pipeline"


async def test_US3_AS3_near_match_other_site_is_candidate_not_merged(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session)
    other = await JobsRepo(db_session).add(
        company_id=None,
        company_name="Aspen Robotics",
        title="Data Engineer",
        city="Pune",
        first_seen_at=NOW,
        last_seen_at=NOW,
        description="",
        state="explore",
    )

    counts = await store(db_session, run_id, [posting(title="Data Engineer ", location="Pune")])

    assert len(await jobs(db_session)) == 2  # a different link: never merged on a guess
    pairs = (await db_session.scalars(select(PossibleDuplicateRow))).all()
    assert len(pairs) == 1
    assert other.id in (pairs[0].job_a_id, pairs[0].job_b_id)
    assert counts.possible_duplicates == 1  # type: ignore[attr-defined]


async def test_US2_AS1_two_jobs_from_one_email_are_both_added(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)

    await store(
        db_session,
        run_id,
        [posting(posting_id="3900000001"), posting(title="QA Engineer", posting_id="3900000002")],
    )

    assert [j.title for j in await jobs(db_session)] == ["Data Engineer", "QA Engineer"]


@pytest.mark.parametrize("bad", ["", "x" * 1200])
async def test_FR013_a_posting_with_no_title_or_an_unusable_link_is_not_stored(
    db_session: AsyncSession, bad: str
) -> None:
    run_id = await make_run(db_session)
    bad_posting = (
        posting(title=bad)
        if bad == ""
        else replace(posting(), clean_link="https://x.invalid/" + bad)
    )

    counts = await store(db_session, run_id, [bad_posting])

    assert await jobs(db_session) == []
    assert counts.new == 0  # type: ignore[attr-defined]


async def test_SEC_two_postings_with_the_same_address_in_one_batch_are_one_job(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session)
    first, second = await message_row(db_session, 1), await message_row(db_session, 2)
    base = posting(message=first)
    # a different clean link, but the same address once the search normalises it
    again = replace(
        posting(message=second), clean_link="https://www.linkedin.com/jobs/view/3978721496?trk=x"
    )

    counts = await store(db_session, run_id, [base, again])

    assert len(await jobs(db_session)) == 1  # no unique violation, no lost batch
    assert await db_session.scalar(select(func.count()).select_from(AlertSightingRow)) == 2
    assert counts.new == 1  # type: ignore[attr-defined]


async def test_SEC_two_postings_with_the_same_site_and_posting_id_in_one_batch_are_one_job(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session)
    first, second = await message_row(db_session, 1), await message_row(db_session, 2)
    other_address = replace(
        posting(message=second), clean_link="https://www.linkedin.com/jobs/view/3978721496/other"
    )

    await store(db_session, run_id, [posting(message=first), other_address])

    assert len(await jobs(db_session)) == 1
    assert await db_session.scalar(select(func.count()).select_from(AlertSightingRow)) == 2
