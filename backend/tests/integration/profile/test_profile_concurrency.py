"""Review fixes: the profile and review tables hold up under concurrent writers."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import (
    Provenance,
    ResumeFilesRepo,
    ReviewsRepo,
    VersionsRepo,
)

PROVENANCE = Provenance("extract_profile", "1", "openai", "gpt-5.4-mini")


def content(name: str) -> ProfileContent:
    return ProfileContent(contact=Contact(name=name))


async def make_review(session: AsyncSession) -> UUID:
    file = await ResumeFilesRepo(session).create(
        kind="upload_pdf", original_name="r.pdf", size_bytes=10, sha256="b" * 64, page_count=1
    )
    run = await RunsRepo(session).create("profile_ingest", subject_id=file.id)
    review = await ReviewsRepo(session).create(
        run_id=run.id,
        resume_file_id=file.id,
        extraction={},
        dropped_items=[],
        flags={},
        provenance=PROVENANCE,
    )
    return review.id


async def test_concurrent_first_versions_get_distinct_numbers(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A manual save racing a confirm, with no profile row yet, must not 500 or lose a number."""

    async def save(name: str) -> int:
        async with sessions() as session:
            version = await VersionsRepo(session).create_version(content(name), created_by="manual")
            await asyncio.sleep(0.2)  # hold the transaction open so the other writer overlaps
            await session.commit()
            return version.number

    numbers = await asyncio.gather(save("A"), save("B"))

    assert sorted(numbers) == [1, 2]
    async with sessions() as session:
        current = await VersionsRepo(session).current()
        assert current is not None
        assert current.number == 2  # the later writer is the current one


async def test_one_review_cannot_produce_two_versions(db_session: AsyncSession) -> None:
    review_id = await make_review(db_session)
    repo = VersionsRepo(db_session)
    await repo.create_version(content("A"), created_by="manual", review_id=review_id)

    with pytest.raises(IntegrityError, match="uq_profile_versions_review_id"):
        await repo.create_version(content("B"), created_by="manual", review_id=review_id)


async def test_extraction_versions_require_provenance(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_profile_versions_extraction_has_provenance"):
        await VersionsRepo(db_session).create_version(content("A"), created_by="extraction")


async def test_closed_review_is_not_reopened_or_redrafted(db_session: AsyncSession) -> None:
    review_id = await make_review(db_session)
    repo = ReviewsRepo(db_session)
    assert await repo.set_status(review_id, "discarded") is True

    assert await repo.set_status(review_id, "confirmed") is False
    assert await repo.set_draft(review_id, content("late autosave")) is None
    review = await repo.get(review_id)
    assert review is not None
    assert review.status == "discarded"
    assert review.draft is None


async def test_open_review_can_still_be_drafted(db_session: AsyncSession) -> None:
    review_id = await make_review(db_session)

    saved_at = await ReviewsRepo(db_session).set_draft(review_id, content("Draft"))

    assert saved_at is not None


@pytest.mark.parametrize(
    "index",
    [
        "ix_profile_reviews_resume_file_id",
        "ix_profile_reviews_compare_to_version_id",
        "ix_profile_versions_source_file_id",
        "ix_profiles_current_version_id",
    ],
)
async def test_foreign_keys_are_indexed(db_session: AsyncSession, index: str) -> None:
    found = await db_session.scalar(
        text("SELECT count(*) FROM pg_indexes WHERE schemaname = 'app' AND indexname = :name"),
        {"name": index},
    )
    assert found == 1
