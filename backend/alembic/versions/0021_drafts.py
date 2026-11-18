"""Job keywords, outreach drafts and tailored resumes (feature 002k).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
KINDS = ("connection_request", "referral_message")
RECIPIENT_KINDS = ("recruiter", "hiring_manager", "engineer", "other")
STATUSES = ("writing", "ready", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _id_and_times() -> list[sa.Column]:  # type: ignore[type-arg]
    now = sa.func.now()
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    ]


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{S}.{target}.id"],
        name=f"fk_{table}_{column}_{target}",
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.create_table(
        "job_keywords",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("description_sha256", sa.Text(), nullable=False),
        sa.Column("role_summary", sa.Text(), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("must_have", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("injection_signals", postgresql.JSONB(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("job_id", name="pk_job_keywords"),
        _fk("job_keywords", "job_id", "jobs", "CASCADE"),
        sa.CheckConstraint(
            "char_length(description_sha256) = 64", name="ck_job_keywords_sha_length"
        ),
        sa.CheckConstraint(
            "char_length(role_summary) <= 160", name="ck_job_keywords_role_summary_length"
        ),
        sa.CheckConstraint("cardinality(keywords) <= 30", name="ck_job_keywords_keywords_count"),
        sa.CheckConstraint("cardinality(must_have) <= 10", name="ck_job_keywords_must_have_count"),
        schema=S,
    )

    op.create_table(
        "outreach_drafts",
        *_id_and_times(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("recipient_contact_id", sa.Uuid()),
        sa.Column("recipient_name", sa.Text(), nullable=False),
        sa.Column("recipient_role", sa.Text()),
        sa.Column("recipient_kind", sa.Text(), nullable=False),
        sa.Column("recipient_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("template", sa.Text()),
        sa.Column("text", sa.Text()),
        sa.Column("source", sa.Text()),
        sa.Column("edited", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cited_fact_ids", postgresql.JSONB(), nullable=False),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("prompt_name", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_outreach_drafts"),
        _fk("outreach_drafts", "job_id", "jobs", "CASCADE"),
        _fk("outreach_drafts", "recipient_contact_id", "company_contacts", "SET NULL"),
        _fk("outreach_drafts", "run_id", "workflow_runs", "SET NULL"),
        sa.UniqueConstraint("job_id", "kind", "recipient_key", name="uq_outreach_drafts_recipient"),
        sa.CheckConstraint(_in("kind", KINDS), name="ck_outreach_drafts_kind_values"),
        sa.CheckConstraint(
            _in("recipient_kind", RECIPIENT_KINDS), name="ck_outreach_drafts_recipient_kind_values"
        ),
        sa.CheckConstraint(_in("status", STATUSES), name="ck_outreach_drafts_status_values"),
        sa.CheckConstraint(
            "source IS NULL OR " + _in("source", ("ai", "fallback")),
            name="ck_outreach_drafts_source_values",
        ),
        sa.CheckConstraint(
            "char_length(recipient_name) BETWEEN 1 AND 120",
            name="ck_outreach_drafts_recipient_name_length",
        ),
        sa.CheckConstraint(
            "char_length(recipient_role) <= 120", name="ck_outreach_drafts_recipient_role_length"
        ),
        sa.CheckConstraint(
            "char_length(template) <= 2000", name="ck_outreach_drafts_template_length"
        ),
        sa.CheckConstraint("char_length(text) <= 2000", name="ck_outreach_drafts_text_length"),
        schema=S,
    )
    op.create_index("ix_outreach_drafts_job_id", "outreach_drafts", ["job_id"], schema=S)

    op.create_table(
        "tailored_resumes",
        *_id_and_times(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version_id", sa.Uuid()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("document", postgresql.JSONB()),
        sa.Column("keyword_match", postgresql.JSONB()),
        sa.Column("source", sa.Text()),
        sa.Column("edited", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("prompt_name", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_tailored_resumes"),
        _fk("tailored_resumes", "job_id", "jobs", "CASCADE"),
        _fk("tailored_resumes", "profile_version_id", "profile_versions", "SET NULL"),
        _fk("tailored_resumes", "run_id", "workflow_runs", "SET NULL"),
        sa.UniqueConstraint("job_id", name="uq_tailored_resumes_job"),
        sa.CheckConstraint(_in("status", STATUSES), name="ck_tailored_resumes_status_values"),
        sa.CheckConstraint(
            "source IS NULL OR " + _in("source", ("ai", "fallback")),
            name="ck_tailored_resumes_source_values",
        ),
        sa.CheckConstraint(
            "document IS NULL OR pg_column_size(document) <= 65536",
            name="ck_tailored_resumes_document_size",
        ),
        schema=S,
    )


def downgrade() -> None:
    op.drop_table("tailored_resumes", schema=S)
    op.drop_index("ix_outreach_drafts_job_id", table_name="outreach_drafts", schema=S)
    op.drop_table("outreach_drafts", schema=S)
    op.drop_table("job_keywords", schema=S)
