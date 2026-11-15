"""The resume a person used for a pipeline job: the database refuses bad rows, and a removed file
leaves its name behind as a note (feature 002f).

Plain SQL again, so the rules hold even if a repository forgets one. The repository's behaviour
is tested further down.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.search.test_schema import job, rejected, run, uid

from hiretitan.search.application.interviews import (
    InterviewInputError,
    JobNotFoundError,
    NotInPipelineError,
)
from hiretitan.search.application.resume_choice import (
    choose_for_job,
    clear_for_job,
    record_on_mark,
)
from hiretitan.search.domain.resume_choice import choice_from
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.pipeline_settings_repo import PipelineSettingsRepo
from hiretitan.search.infra.repos import JobsRepo
from hiretitan.search_wiring import SqlResumeLookup

FILE = (
    "INSERT INTO app.resume_files (id, kind, original_name, size_bytes, sha256, parse_status) "
    "VALUES (:id, 'upload_pdf', :name, 1000, :sha, :status)"
)
DETAILS = "INSERT INTO app.job_pipeline_details (job_id{cols}) VALUES (:job{vals})"
SETTINGS = "INSERT INTO app.pipeline_settings (id, last_resume_file_id) VALUES (:id, :file)"


def details_sql(cols: str = "", vals: str = "") -> str:
    return DETAILS.format(cols=f", {cols}" if cols else "", vals=f", {vals}" if vals else "")


async def a_job(session: AsyncSession) -> str:
    return await job(session, "applied_on", "current_date", state="applied")


async def a_file(
    session: AsyncSession, name: str = "Backend_2025.pdf", status: str = "parsed"
) -> str:
    file_id = uid()
    await run(session, FILE, id=file_id, name=name, sha="a" * 64, status=status)
    return file_id


async def test_resume_columns_constraints(db_session: AsyncSession) -> None:
    job_id = await a_job(db_session)
    file_id = await a_file(db_session)
    cols = "resume_file_id, resume_name, resume_added_on"

    # a name needs its day, and the other way round
    await rejected(db_session, details_sql("resume_name", "'a.pdf'"), job=job_id)
    await rejected(db_session, details_sql("resume_added_on", "current_date"), job=job_id)
    # a link to a file needs the snapshot of its name
    await rejected(db_session, details_sql("resume_file_id", ":file"), job=job_id, file=file_id)
    # the name is 1 to 255 characters
    await rejected(
        db_session, details_sql("resume_name, resume_added_on", "'', current_date"), job=job_id
    )
    await rejected(
        db_session,
        details_sql("resume_name, resume_added_on", ":name, current_date"),
        job=job_id,
        name="n" * 256,
    )
    # a link to a file that does not exist
    await rejected(
        db_session,
        details_sql(cols, ":file, 'a.pdf', current_date"),
        job=job_id,
        file=uid(),
    )

    # the good shapes: a link with its snapshot, and a snapshot alone (a removed note)
    await run(
        db_session, details_sql(cols, ":file, 'a.pdf', current_date"), job=job_id, file=file_id
    )
    other = await a_job(db_session)
    await run(
        db_session, details_sql("resume_name, resume_added_on", "'b.pdf', current_date"), job=other
    )


async def test_FR009_removing_a_file_keeps_its_name_as_a_removed_note(
    db_session: AsyncSession,
) -> None:
    job_id = await a_job(db_session)
    file_id = await a_file(db_session, "Backend_2024.pdf")
    await run(
        db_session,
        details_sql(
            "resume_file_id, resume_name, resume_added_on",
            ":file, 'Backend_2024.pdf', '2025-03-14'",
        ),
        job=job_id,
        file=file_id,
    )

    await run(db_session, "DELETE FROM app.resume_files WHERE id = :id", id=file_id)

    row = (
        await db_session.execute(
            text(
                "SELECT resume_file_id, resume_name, resume_added_on::text "
                "FROM app.job_pipeline_details WHERE job_id = :job"
            ),
            {"job": job_id},
        )
    ).one()
    assert row == (None, "Backend_2024.pdf", "2025-03-14")


async def test_FR014_pipeline_settings_is_one_row_and_resets_with_its_file(
    db_session: AsyncSession,
) -> None:
    file_id = await a_file(db_session)

    await rejected(db_session, SETTINGS, id=2, file=None)  # only row 1 exists
    await rejected(db_session, SETTINGS, id=1, file=uid())  # the file must exist
    await run(db_session, SETTINGS, id=1, file=file_id)
    await rejected(db_session, SETTINGS, id=1, file=None)  # and there is only one

    await run(db_session, "DELETE FROM app.resume_files WHERE id = :id", id=file_id)
    last = (
        await db_session.execute(
            text("SELECT last_resume_file_id FROM app.pipeline_settings WHERE id = 1")
        )
    ).scalar_one()
    assert last is None


# --- the repositories ------------------------------------------------------------------------

ADDED = date(2025, 3, 14)


async def test_prune_keeps_a_row_whose_only_detail_is_the_resume(db_session: AsyncSession) -> None:
    repo = InterviewsRepo(db_session)
    job_id = UUID(await a_job(db_session))
    file_id = UUID(await a_file(db_session))
    await repo.set_resume(job_id, file_id, "Backend_2025.pdf", ADDED)

    # an empty source and an empty contact would have dropped the row before this feature
    await repo.set_source(job_id, None, None)
    await repo.clear_contact(job_id)

    row = (await repo.details(job_id)).details
    assert row is not None
    assert (row.resume_file_id, row.resume_name, row.resume_added_on) == (
        file_id,
        "Backend_2025.pdf",
        ADDED,
    )


async def test_clear_resume_prunes_an_otherwise_empty_row(db_session: AsyncSession) -> None:
    repo = InterviewsRepo(db_session)
    alone = UUID(await a_job(db_session))
    with_contact = UUID(await a_job(db_session))
    file_id = UUID(await a_file(db_session))
    for job_id in (alone, with_contact):
        await repo.set_resume(job_id, file_id, "Backend_2025.pdf", ADDED)
    await repo.set_source(with_contact, "direct", None)

    await repo.clear_resume(alone)
    await repo.clear_resume(with_contact)

    assert (await repo.details(alone)).details is None  # nothing left, so the row is gone
    kept = (await repo.details(with_contact)).details
    assert kept is not None
    assert kept.source == "direct"
    assert (kept.resume_file_id, kept.resume_name, kept.resume_added_on) == (None, None, None)


async def test_set_resume_replaces_a_removed_note(db_session: AsyncSession) -> None:
    repo = InterviewsRepo(db_session)
    job_id = UUID(await a_job(db_session))
    old = UUID(await a_file(db_session, "Old.pdf"))
    new = UUID(await a_file(db_session, "New.pdf"))
    await repo.set_resume(job_id, old, "Old.pdf", ADDED)
    await run(db_session, "DELETE FROM app.resume_files WHERE id = :id", id=old)

    await repo.set_resume(job_id, new, "New.pdf", date(2026, 1, 5))

    row = (await repo.details(job_id)).details
    assert row is not None
    assert choice_from(row.resume_file_id, row.resume_name, row.resume_added_on).state == "chosen"
    assert row.resume_name == "New.pdf"


async def test_FR009_usage_counts_jobs_per_file(db_session: AsyncSession) -> None:
    repo = InterviewsRepo(db_session)
    first = UUID(await a_file(db_session, "A.pdf"))
    second = UUID(await a_file(db_session, "B.pdf"))
    unused = UUID(await a_file(db_session, "C.pdf"))
    for file_id, name in ((first, "A.pdf"), (first, "A.pdf"), (second, "B.pdf")):
        await repo.set_resume(UUID(await a_job(db_session)), file_id, name, ADDED)
    # a removed note points at no file, so it is not counted
    gone = UUID(await a_job(db_session))
    await repo.set_resume(gone, UUID(await a_file(db_session, "D.pdf")), "D.pdf", ADDED)
    await run(db_session, "DELETE FROM app.resume_files WHERE original_name = 'D.pdf'")

    usage = await repo.usage()

    assert usage == {first: 2, second: 1}
    assert unused not in usage


async def test_last_choice_round_trip(db_session: AsyncSession) -> None:
    settings = PipelineSettingsRepo(db_session)
    file_id = UUID(await a_file(db_session))
    assert await settings.last_choice() is None  # no row yet means None

    await settings.set_last_choice(file_id)
    assert await settings.last_choice() == file_id

    await settings.set_last_choice(None)  # an explicit None is remembered too
    assert await settings.last_choice() is None


async def test_FR014_last_choice_resets_when_its_file_is_removed(db_session: AsyncSession) -> None:
    settings = PipelineSettingsRepo(db_session)
    file_id = UUID(await a_file(db_session))
    await settings.set_last_choice(file_id)

    await run(db_session, "DELETE FROM app.resume_files WHERE id = :id", id=file_id)

    assert await settings.last_choice() is None


async def test_FR009_a_removed_file_shows_as_a_removed_note_through_the_repo(
    db_session: AsyncSession,
) -> None:
    repo = InterviewsRepo(db_session)
    job_id = UUID(await a_job(db_session))
    file_id = UUID(await a_file(db_session, "Backend_2024.pdf"))
    await repo.set_resume(job_id, file_id, "Backend_2024.pdf", ADDED)

    await run(db_session, "DELETE FROM app.resume_files WHERE id = :id", id=file_id)
    db_session.expire_all()

    row = (await repo.details(job_id)).details
    assert row is not None
    choice = choice_from(row.resume_file_id, row.resume_name, row.resume_added_on)
    assert (choice.state, choice.name, choice.added_on) == ("removed", "Backend_2024.pdf", ADDED)


# --- the use cases and the file lookup -------------------------------------------------------


async def test_sql_resume_lookup_reads_name_day_and_offerable(db_session: AsyncSession) -> None:
    lookup = SqlResumeLookup(db_session)
    good = UUID(await a_file(db_session, "Backend_2025.pdf", "parsed"))
    reading = UUID(await a_file(db_session, "New.pdf", "pending"))
    letter = UUID(await a_file(db_session, "Letter.pdf", "not_resume"))

    found = await lookup.get(good)
    assert found is not None
    assert (found.name, found.offerable) == ("Backend_2025.pdf", True)
    assert found.added_on == datetime.now(UTC).date()  # the day the row was created (UTC)
    still_reading = await lookup.get(reading)
    assert still_reading is not None
    assert still_reading.offerable  # FR-012: only not_resume is out
    refused = await lookup.get(letter)
    assert refused is not None
    assert not refused.offerable
    assert await lookup.get(UUID(uid())) is None


async def test_FR001_choose_for_job_records_the_file(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    job_id = UUID(await a_job(db_session))
    file_id = UUID(await a_file(db_session, "Backend_2025.pdf"))

    choice = await choose_for_job(jobs, lookup, repo, job_id, file_id)

    assert (choice.state, choice.resume_file_id, choice.name) == (
        "chosen",
        file_id,
        "Backend_2025.pdf",
    )
    row = (await repo.details(job_id)).details
    assert row is not None
    assert row.resume_name == "Backend_2025.pdf"


async def test_FR001_unknown_file_is_a_field_error(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    job_id = UUID(await a_job(db_session))

    with pytest.raises(InterviewInputError) as raised:
        await choose_for_job(jobs, lookup, repo, job_id, UUID(uid()))

    assert [e.field for e in raised.value.errors] == ["resume_file_id"]
    assert (await repo.details(job_id)).details is None  # nothing was saved


async def test_FR012_not_a_resume_file_is_refused(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    job_id = UUID(await a_job(db_session))
    letter = UUID(await a_file(db_session, "Letter.pdf", "not_resume"))

    with pytest.raises(InterviewInputError) as raised:
        await choose_for_job(jobs, lookup, repo, job_id, letter)

    assert [e.field for e in raised.value.errors] == ["resume_file_id"]


async def test_choose_and_clear_need_a_pipeline_job(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    explore = UUID(await job(db_session))  # not applied or inquired
    file_id = UUID(await a_file(db_session))

    with pytest.raises(NotInPipelineError):
        await choose_for_job(jobs, lookup, repo, explore, file_id)
    with pytest.raises(NotInPipelineError):
        await clear_for_job(jobs, repo, explore)
    with pytest.raises(JobNotFoundError):
        await clear_for_job(jobs, repo, UUID(uid()))


async def test_clear_for_job_forgets_the_resume(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    job_id = UUID(await a_job(db_session))
    file_id = UUID(await a_file(db_session))
    await choose_for_job(jobs, lookup, repo, job_id, file_id)

    await clear_for_job(jobs, repo, job_id)

    assert (await repo.details(job_id)).details is None


async def test_record_on_mark_absent_changes_nothing(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    settings = PipelineSettingsRepo(db_session)
    job_id = UUID(await a_job(db_session))
    mine = UUID(await a_file(db_session, "Mine.pdf"))
    last = UUID(await a_file(db_session, "Last.pdf"))
    await choose_for_job(jobs, lookup, repo, job_id, mine)
    await settings.set_last_choice(last)

    await record_on_mark(jobs, lookup, repo, settings, job_id, provided=False, file_id=None)

    row = (await repo.details(job_id)).details
    assert row is not None
    assert row.resume_file_id == mine  # inquired to applied keeps it (FR-003)
    assert await settings.last_choice() == last


async def test_record_on_mark_with_a_file_sets_the_job_and_the_last_choice(
    db_session: AsyncSession,
) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    settings = PipelineSettingsRepo(db_session)
    job_id = UUID(await a_job(db_session))
    file_id = UUID(await a_file(db_session, "Backend_2025.pdf"))

    await record_on_mark(jobs, lookup, repo, settings, job_id, provided=True, file_id=file_id)

    row = (await repo.details(job_id)).details
    assert row is not None
    assert row.resume_file_id == file_id
    assert await settings.last_choice() == file_id


async def test_record_on_mark_null_sets_none(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    settings = PipelineSettingsRepo(db_session)
    job_id = UUID(await a_job(db_session))
    file_id = UUID(await a_file(db_session))
    await choose_for_job(jobs, lookup, repo, job_id, file_id)
    await settings.set_last_choice(file_id)

    await record_on_mark(jobs, lookup, repo, settings, job_id, provided=True, file_id=None)

    assert (await repo.details(job_id)).details is None  # the job's resume is cleared
    assert await settings.last_choice() is None  # and None is what the next mark starts on


async def test_record_on_mark_with_a_bad_file_saves_nothing(db_session: AsyncSession) -> None:
    repo, jobs, lookup = (
        InterviewsRepo(db_session),
        JobsRepo(db_session),
        SqlResumeLookup(db_session),
    )
    settings = PipelineSettingsRepo(db_session)
    job_id = UUID(await a_job(db_session))
    last = UUID(await a_file(db_session))
    await settings.set_last_choice(last)

    with pytest.raises(InterviewInputError):
        await record_on_mark(
            jobs, lookup, repo, settings, job_id, provided=True, file_id=UUID(uid())
        )

    assert (await repo.details(job_id)).details is None
    assert await settings.last_choice() == last
