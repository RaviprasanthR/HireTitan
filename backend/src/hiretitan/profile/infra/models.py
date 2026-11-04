"""ORM models for the profile module's tables (data-model.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import APP_SCHEMA, Base, IdTimestampMixin, uuid7

JsonDict = dict[str, Any]


class ResumeFileRow(Base):
    __tablename__ = "resume_files"
    __table_args__ = (
        CheckConstraint("kind IN ('upload_pdf', 'upload_docx', 'pasted_text')", name="kind_values"),
        CheckConstraint("char_length(original_name) <= 255", name="original_name_length"),
        CheckConstraint("size_bytes BETWEEN 1 AND 5242880", name="size_bytes_range"),
        CheckConstraint("char_length(sha256) = 64", name="sha256_length"),
        CheckConstraint(
            "page_count IS NULL OR page_count BETWEEN 1 AND 20", name="page_count_range"
        ),
        CheckConstraint(
            "parse_status IN ('pending', 'parsed', 'no_text', 'failed')", name="parse_status_values"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(Text, server_default="pending")
    parse_result: Mapped[JsonDict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileReviewRow(IdTimestampMixin, Base):
    __tablename__ = "profile_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'confirmed', 'discarded')", name="status_values"),
        UniqueConstraint("run_id", name="uq_profile_reviews_run_id"),
        # At most one open review at any time.
        Index(
            "uq_profile_reviews_one_open",
            "status",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_profile_reviews_resume_file_id", "resume_file_id"),
        Index("ix_profile_reviews_compare_to_version_id", "compare_to_version_id"),
    )

    run_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.workflow_runs.id"))
    resume_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.resume_files.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(Text, server_default="open")
    extraction: Mapped[JsonDict] = mapped_column(JSONB)
    dropped_items: Mapped[list[JsonDict]] = mapped_column(JSONB)
    flags: Mapped[JsonDict] = mapped_column(JSONB)
    compare_to_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.profile_versions.id", use_alter=True)
    )
    changed_paths: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    draft: Mapped[JsonDict | None] = mapped_column(JSONB)
    draft_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prompt_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)


class ProfileRow(IdTimestampMixin, Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("singleton", name="singleton"),
        UniqueConstraint("singleton", name="uq_profiles_singleton"),
        Index("ix_profiles_current_version_id", "current_version_id"),
    )

    singleton: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    current_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.profile_versions.id", use_alter=True)
    )


class ProfileVersionRow(Base):
    __tablename__ = "profile_versions"
    __table_args__ = (
        CheckConstraint(
            "created_by IN ('extraction', 'manual', 'manual_edit')", name="created_by_values"
        ),
        CheckConstraint(
            "created_by <> 'extraction' OR prompt_name IS NOT NULL",
            name="extraction_has_provenance",
        ),
        UniqueConstraint("profile_id", "number", name="uq_profile_versions_profile_id_number"),
        # One confirmed version per review, so a retried or doubled confirm cannot add a second.
        Index(
            "uq_profile_versions_review_id",
            "review_id",
            unique=True,
            postgresql_where=text("review_id IS NOT NULL"),
        ),
        Index("ix_profile_versions_source_file_id", "source_file_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.profiles.id"))
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[JsonDict] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(Text)
    source_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.resume_files.id", ondelete="SET NULL")
    )
    source_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    review_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.profile_reviews.id", ondelete="SET NULL", use_alter=True)
    )
    prompt_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
