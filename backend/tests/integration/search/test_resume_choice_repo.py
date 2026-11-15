"""The resume a person used for a pipeline job: the database refuses bad rows, and a removed file
leaves its name behind as a note (feature 002f).

Plain SQL again, so the rules hold even if a repository forgets one. The repository's behaviour
is tested further down.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.search.test_schema import job, rejected, run, uid

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
