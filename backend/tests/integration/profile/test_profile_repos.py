"""T041: the profile tables and repositories (FR-012, FR-017, FR-034)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.domain.content import Contact, Experience, ProfileContent, YearMonth
from hiretitan.profile.infra.repos import (
    Provenance,
    ResumeFilesRepo,
    ReviewsRepo,
    VersionsRepo,
)

SHA = "a" * 64
PROVENANCE = Provenance("extract_profile", "1", "openai", "gpt-5.4-mini")


def content(name: str = "Jane Example") -> ProfileContent:
    job = Experience(employer="Acme", title="Engineer", start=YearMonth(2021, 1))
    return ProfileContent(contact=Contact(name=name), experience=(job,), skills=("Python",))


async def make_file(session: AsyncSession, sha: str = SHA) -> UUID:
    row = await ResumeFilesRepo(session).create(
        kind="upload_pdf", original_name="resume.pdf", size_bytes=1234, sha256=sha, page_count=2
    )
    return row.id


async def make_review(session: AsyncSession, file_id: UUID, *, status: str = "open") -> UUID:
    run = await RunsRepo(session).create("profile_ingest", subject_id=file_id)
    review = await ReviewsRepo(session).create(
        run_id=run.id,
        resume_file_id=file_id,
        extraction={"contact": {"name": "Jane"}},
        dropped_items=[],
        flags={"hidden_text": [], "injection_flags": [], "truncated_at": None},
        provenance=PROVENANCE,
    )
    if status != "open":
        await ReviewsRepo(session).set_status(review.id, status)
    return review.id


async def test_resume_file_roundtrip_and_parse_result(db_session: AsyncSession) -> None:
    repo = ResumeFilesRepo(db_session)
    file_id = await make_file(db_session)
    await repo.set_parse_result(file_id, "parsed", {"visible_text_chars": 1500})
    row = await repo.get(file_id)
    assert row is not None
    assert (row.parse_status, row.parse_result) == ("parsed", {"visible_text_chars": 1500})
    assert [f.id for f in await repo.list()] == [file_id]


@pytest.mark.parametrize(
    "overrides",
    [
        {"size_bytes": 0},
        {"size_bytes": 5_242_881},
        {"sha256": "short"},
        {"kind": "upload_exe"},
        {"page_count": 21},
        {"original_name": "x" * 256},
    ],
)
async def test_resume_file_rules_enforced_by_the_database(
    db_session: AsyncSession, overrides: dict[str, object]
) -> None:
    values: dict[str, object] = {
        "kind": "upload_pdf",
        "original_name": "r.pdf",
        "size_bytes": 10,
        "sha256": SHA,
        "page_count": 1,
    }
    values.update(overrides)
    with pytest.raises(IntegrityError):
        await ResumeFilesRepo(db_session).create(**values)  # type: ignore[arg-type]


async def test_edge_case_only_one_open_review(db_session: AsyncSession) -> None:
    first_file = await make_file(db_session)
    await make_review(db_session, first_file)
    assert (await ReviewsRepo(db_session).get_open()) is not None
    second_file = await make_file(db_session, "b" * 64)
    with pytest.raises(IntegrityError):
        await make_review(db_session, second_file)


async def test_a_new_review_is_allowed_once_the_old_one_is_closed(db_session: AsyncSession) -> None:
    first = await make_review(db_session, await make_file(db_session), status="discarded")
    second = await make_review(db_session, await make_file(db_session, "b" * 64))
    open_review = await ReviewsRepo(db_session).get_open()
    assert open_review is not None
    assert open_review.id == second != first


async def test_draft_is_saved_with_a_timestamp(db_session: AsyncSession) -> None:
    review_id = await make_review(db_session, await make_file(db_session))
    repo = ReviewsRepo(db_session)
    await repo.set_draft(review_id, content("Draft Name"))
    review = await repo.get(review_id)
    assert review is not None
    assert review.draft == content("Draft Name") or review.draft is not None
    assert review.draft is not None
    assert review.draft.contact.name == "Draft Name"
    assert review.draft_saved_at is not None


async def test_version_numbers_increment(db_session: AsyncSession) -> None:
    repo = VersionsRepo(db_session)
    one = await repo.create_version(content(), created_by="manual")
    two = await repo.create_version(content("Jane B"), created_by="manual_edit")
    assert (one.number, two.number) == (1, 2)
    assert (await repo.current()).id == two.id  # type: ignore[union-attr]
    assert [v.number for v in await repo.list_versions()] == [2, 1]


async def test_FR017_version_content_immutable(db_session: AsyncSession) -> None:
    version = await VersionsRepo(db_session).create_version(content(), created_by="manual")
    with pytest.raises(DBAPIError, match="immutable"):
        await db_session.execute(
            text("UPDATE app.profile_versions SET content = '{}'::jsonb WHERE id = :id"),
            {"id": version.id},
        )


async def test_FR017_a_version_cannot_be_deleted(db_session: AsyncSession) -> None:
    version = await VersionsRepo(db_session).create_version(content(), created_by="manual")
    with pytest.raises(DBAPIError, match="immutable"):
        await db_session.execute(
            text("DELETE FROM app.profile_versions WHERE id = :id"), {"id": version.id}
        )


@pytest.mark.parametrize(
    "assignment",
    ["number = 99", "created_by = 'manual'", "provider = 'x'", "source_deleted = false"],
)
async def test_other_columns_are_immutable_too(db_session: AsyncSession, assignment: str) -> None:
    file_id = await make_file(db_session)
    version = await VersionsRepo(db_session).create_version(
        content(), created_by="extraction", source_file_id=file_id, provenance=PROVENANCE
    )
    await db_session.execute(
        text("UPDATE app.profile_versions SET source_deleted = true WHERE id = :id"),
        {"id": version.id},
    )
    with pytest.raises(DBAPIError, match="immutable"):
        await db_session.execute(
            text(f"UPDATE app.profile_versions SET {assignment} WHERE id = :id"),
            {"id": version.id},
        )


async def test_FR034_file_delete_nulls_version_source(db_session: AsyncSession) -> None:
    files = ResumeFilesRepo(db_session)
    file_id = await make_file(db_session)
    review_id = await make_review(db_session, file_id, status="confirmed")
    version = await VersionsRepo(db_session).create_version(
        content(),
        created_by="extraction",
        source_file_id=file_id,
        review_id=review_id,
        provenance=PROVENANCE,
    )

    await files.delete(file_id)

    again = await VersionsRepo(db_session).get(version.id)
    assert again is not None
    assert again.source_file_id is None
    assert again.review_id is None  # the review went with its file
    assert again.source_deleted is True
    assert again.content == content() or again.content.contact.name == "Jane Example"
    assert await ReviewsRepo(db_session).get(review_id) is None
    assert await files.get(file_id) is None


async def test_FR012_extraction_version_keeps_provenance_after_file_delete(
    db_session: AsyncSession,
) -> None:
    file_id = await make_file(db_session)
    version = await VersionsRepo(db_session).create_version(
        content(), created_by="extraction", source_file_id=file_id, provenance=PROVENANCE
    )
    await ResumeFilesRepo(db_session).delete(file_id)

    again = await VersionsRepo(db_session).get(version.id)
    assert again is not None
    assert again.provenance == PROVENANCE
    assert again.created_by == "extraction"


async def test_manual_versions_have_no_provenance(db_session: AsyncSession) -> None:
    version = await VersionsRepo(db_session).create_version(content(), created_by="manual")
    assert version.provenance is None


async def test_profile_is_a_singleton(db_session: AsyncSession) -> None:
    await VersionsRepo(db_session).create_version(content(), created_by="manual")
    count = (await db_session.execute(text("SELECT count(*) FROM app.profiles"))).scalar_one()
    assert count == 1
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO app.profiles (id, singleton) VALUES (gen_random_uuid(), true)")
        )
