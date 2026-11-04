"""Repositories for the profile tables. They speak domain types and plain dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.profile.domain.content import ProfileContent
from hiretitan.profile.domain.serialization import content_from_json, content_to_json
from hiretitan.profile.infra.models import (
    ProfileReviewRow,
    ProfileRow,
    ProfileVersionRow,
    ResumeFileRow,
)

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Provenance:
    """Which prompt and model produced an AI result (FR-012)."""

    prompt_name: str
    prompt_version: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class ResumeFile:
    id: UUID
    kind: str
    original_name: str
    size_bytes: int
    sha256: str
    page_count: int | None
    parse_status: str
    parse_result: JsonDict | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Review:
    id: UUID
    run_id: UUID
    resume_file_id: UUID | None
    status: str
    extraction: JsonDict
    dropped_items: list[JsonDict]
    flags: JsonDict
    compare_to_version_id: UUID | None
    changed_paths: list[str]
    draft: ProfileContent | None
    draft_saved_at: datetime | None
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class Version:
    id: UUID
    number: int
    content: ProfileContent
    created_by: str
    source_file_id: UUID | None
    source_deleted: bool
    review_id: UUID | None
    provenance: Provenance | None
    created_at: datetime


class ResumeFilesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_file(row: ResumeFileRow) -> ResumeFile:
        return ResumeFile(
            row.id,
            row.kind,
            row.original_name,
            row.size_bytes,
            row.sha256,
            row.page_count,
            row.parse_status,
            row.parse_result,
            row.created_at,
        )

    async def create(
        self,
        *,
        kind: str,
        original_name: str,
        size_bytes: int,
        sha256: str,
        page_count: int | None = None,
    ) -> ResumeFile:
        row = ResumeFileRow(
            kind=kind,
            original_name=original_name,
            size_bytes=size_bytes,
            sha256=sha256,
            page_count=page_count,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_file(row)

    async def get(self, file_id: UUID) -> ResumeFile | None:
        row = await self._session.get(ResumeFileRow, file_id)
        return self._to_file(row) if row else None

    async def list(self) -> list[ResumeFile]:
        rows = await self._session.scalars(select(ResumeFileRow).order_by(ResumeFileRow.id.desc()))
        return [self._to_file(r) for r in rows]

    async def set_parse_result(
        self, file_id: UUID, status: str, result: JsonDict, page_count: int | None = None
    ) -> None:
        values: JsonDict = {"parse_status": status, "parse_result": result}
        if page_count is not None:
            values["page_count"] = page_count
        await self._session.execute(
            update(ResumeFileRow).where(ResumeFileRow.id == file_id).values(**values)
        )

    async def delete(self, file_id: UUID) -> None:
        """Delete a file, its review (cascade) and mark versions made from it (FR-034).

        The versions keep their content and AI provenance; their link to the file and review
        is cleared by the foreign keys.
        """
        await self._session.execute(
            update(ProfileVersionRow)
            .where(ProfileVersionRow.source_file_id == file_id)
            .values(source_deleted=True)
        )
        await self._session.execute(delete(ResumeFileRow).where(ResumeFileRow.id == file_id))
        await self._session.flush()
        self._session.expire_all()


class ReviewsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_review(row: ProfileReviewRow) -> Review:
        return Review(
            id=row.id,
            run_id=row.run_id,
            resume_file_id=row.resume_file_id,
            status=row.status,
            extraction=row.extraction,
            dropped_items=row.dropped_items,
            flags=row.flags,
            compare_to_version_id=row.compare_to_version_id,
            changed_paths=row.changed_paths,
            draft=content_from_json(row.draft) if row.draft else None,
            draft_saved_at=row.draft_saved_at,
            provenance=Provenance(row.prompt_name, row.prompt_version, row.provider, row.model),
        )

    async def create(
        self,
        *,
        run_id: UUID,
        resume_file_id: UUID,
        extraction: JsonDict,
        dropped_items: list[JsonDict],
        flags: JsonDict,
        provenance: Provenance,
        compare_to_version_id: UUID | None = None,
        changed_paths: list[str] | None = None,
    ) -> Review:
        row = ProfileReviewRow(
            run_id=run_id,
            resume_file_id=resume_file_id,
            status="open",
            extraction=extraction,
            dropped_items=dropped_items,
            flags=flags,
            compare_to_version_id=compare_to_version_id,
            changed_paths=changed_paths or [],
            prompt_name=provenance.prompt_name,
            prompt_version=provenance.prompt_version,
            provider=provenance.provider,
            model=provenance.model,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_review(row)

    async def get(self, review_id: UUID) -> Review | None:
        row = await self._session.get(ProfileReviewRow, review_id, populate_existing=True)
        return self._to_review(row) if row else None

    async def get_by_run(self, run_id: UUID) -> Review | None:
        row = await self._session.scalar(
            select(ProfileReviewRow).where(ProfileReviewRow.run_id == run_id)
        )
        return self._to_review(row) if row else None

    async def get_open(self) -> Review | None:
        row = await self._session.scalar(
            select(ProfileReviewRow).where(ProfileReviewRow.status == "open")
        )
        return self._to_review(row) if row else None

    async def set_draft(self, review_id: UUID, content: ProfileContent) -> datetime:
        saved_at = datetime.now(UTC)
        await self._session.execute(
            update(ProfileReviewRow)
            .where(ProfileReviewRow.id == review_id)
            .values(draft=content_to_json(content), draft_saved_at=saved_at)
        )
        return saved_at

    async def set_status(self, review_id: UUID, status: str) -> None:
        await self._session.execute(
            update(ProfileReviewRow).where(ProfileReviewRow.id == review_id).values(status=status)
        )
        await self._session.flush()


class VersionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_version(row: ProfileVersionRow) -> Version:
        provenance = (
            Provenance(
                row.prompt_name, row.prompt_version or "", row.provider or "", row.model or ""
            )
            if row.prompt_name
            else None
        )
        return Version(
            id=row.id,
            number=row.number,
            content=content_from_json(row.content),
            created_by=row.created_by,
            source_file_id=row.source_file_id,
            source_deleted=row.source_deleted,
            review_id=row.review_id,
            provenance=provenance,
            created_at=row.created_at,
        )

    async def _profile(self) -> ProfileRow:
        row = await self._session.scalar(select(ProfileRow))
        if row is None:
            row = ProfileRow()
            self._session.add(row)
            await self._session.flush()
        return row

    async def create_version(
        self,
        content: ProfileContent,
        *,
        created_by: str,
        source_file_id: UUID | None = None,
        review_id: UUID | None = None,
        provenance: Provenance | None = None,
    ) -> Version:
        profile = await self._profile()
        latest = await self._session.scalar(
            select(func.coalesce(func.max(ProfileVersionRow.number), 0)).where(
                ProfileVersionRow.profile_id == profile.id
            )
        )
        row = ProfileVersionRow(
            profile_id=profile.id,
            number=(latest or 0) + 1,
            content=content_to_json(content),
            created_by=created_by,
            source_file_id=source_file_id,
            review_id=review_id,
            prompt_name=provenance.prompt_name if provenance else None,
            prompt_version=provenance.prompt_version if provenance else None,
            provider=provenance.provider if provenance else None,
            model=provenance.model if provenance else None,
        )
        self._session.add(row)
        await self._session.flush()
        profile.current_version_id = row.id
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_version(row)

    async def get(self, version_id: UUID) -> Version | None:
        row = await self._session.get(ProfileVersionRow, version_id, populate_existing=True)
        return self._to_version(row) if row else None

    async def current_content(self) -> ProfileContent | None:
        """Implements ``CurrentProfileReader``: only the confirmed current version."""
        current = await self.current()
        return current.content if current else None

    async def get_by_review(self, review_id: UUID) -> Version | None:
        row = await self._session.scalar(
            select(ProfileVersionRow).where(ProfileVersionRow.review_id == review_id)
        )
        return self._to_version(row) if row else None

    async def current(self) -> Version | None:
        profile = await self._session.scalar(select(ProfileRow))
        if profile is None or profile.current_version_id is None:
            return None
        return await self.get(profile.current_version_id)

    async def list_versions(self) -> list[Version]:
        rows = await self._session.scalars(
            select(ProfileVersionRow).order_by(ProfileVersionRow.number.desc())
        )
        return [self._to_version(r) for r in rows]
