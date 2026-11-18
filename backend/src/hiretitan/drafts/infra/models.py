"""ORM models for the drafts module's tables (data-model.md, migration 0021).

The database repeats every rule as a named constraint, so a repository bug cannot store a value
the model forbids.
"""

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
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import APP_SCHEMA, Base, IdTimestampMixin

DRAFT_KINDS = ("connection_request", "referral_message")
RECIPIENT_KINDS = ("recruiter", "hiring_manager", "engineer", "other")
DRAFT_STATUSES = ("writing", "ready", "failed")
DRAFT_SOURCES = ("ai", "fallback")
DOCUMENT_MAX_BYTES = 64 * 1024


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class JobKeywordsRow(Base):
    """What the job's description asks for, read once per description (research R3)."""

    __tablename__ = "job_keywords"
    __table_args__ = (
        CheckConstraint("char_length(description_sha256) = 64", name="sha_length"),
        CheckConstraint("char_length(role_summary) <= 160", name="role_summary_length"),
        CheckConstraint("cardinality(keywords) <= 30", name="keywords_count"),
        CheckConstraint("cardinality(must_have) <= 10", name="must_have_count"),
    )

    job_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="CASCADE"), primary_key=True
    )
    description_sha256: Mapped[str] = mapped_column(Text)
    role_summary: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text))
    must_have: Mapped[list[str]] = mapped_column(ARRAY(Text))
    injection_signals: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    prompt_version: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OutreachDraftRow(IdTimestampMixin, Base):
    """One message draft for a job and a recipient. Never sent by the app (constitution I)."""

    __tablename__ = "outreach_drafts"
    __table_args__ = (
        UniqueConstraint("job_id", "kind", "recipient_key", name="uq_outreach_drafts_recipient"),
        CheckConstraint(_in("kind", DRAFT_KINDS), name="kind_values"),
        CheckConstraint(_in("recipient_kind", RECIPIENT_KINDS), name="recipient_kind_values"),
        CheckConstraint(_in("status", DRAFT_STATUSES), name="status_values"),
        CheckConstraint("source IS NULL OR " + _in("source", DRAFT_SOURCES), name="source_values"),
        CheckConstraint(
            "char_length(recipient_name) BETWEEN 1 AND 120", name="recipient_name_length"
        ),
        CheckConstraint("char_length(recipient_role) <= 120", name="recipient_role_length"),
        CheckConstraint("char_length(template) <= 2000", name="template_length"),
        CheckConstraint("char_length(text) <= 2000", name="text_length"),
        Index("ix_outreach_drafts_job_id", "job_id"),
        Index(
            "ix_outreach_drafts_recipient_contact_id",
            "recipient_contact_id",
            postgresql_where=text("recipient_contact_id IS NOT NULL"),
        ),
        Index("ix_outreach_drafts_run_id", "run_id", postgresql_where=text("run_id IS NOT NULL")),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    recipient_contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.company_contacts.id", ondelete="SET NULL")
    )
    recipient_name: Mapped[str] = mapped_column(Text)
    recipient_role: Mapped[str | None] = mapped_column(Text)
    recipient_kind: Mapped[str] = mapped_column(Text)
    recipient_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.workflow_runs.id", ondelete="SET NULL")
    )
    template: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cited_fact_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    prompt_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)


class TailoredResumeRow(IdTimestampMixin, Base):
    """The resume tailored to one job, built from the confirmed profile only."""

    __tablename__ = "tailored_resumes"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_tailored_resumes_job"),
        CheckConstraint(_in("status", DRAFT_STATUSES), name="status_values"),
        CheckConstraint("source IS NULL OR " + _in("source", DRAFT_SOURCES), name="source_values"),
        CheckConstraint(
            f"document IS NULL OR octet_length(document::text) <= {DOCUMENT_MAX_BYTES}",
            name="document_size",
        ),
        Index("ix_tailored_resumes_run_id", "run_id", postgresql_where=text("run_id IS NOT NULL")),
        Index(
            "ix_tailored_resumes_profile_version_id",
            "profile_version_id",
            postgresql_where=text("profile_version_id IS NOT NULL"),
        ),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="CASCADE"))
    profile_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.profile_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.workflow_runs.id", ondelete="SET NULL")
    )
    document: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    keyword_match: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    prompt_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
