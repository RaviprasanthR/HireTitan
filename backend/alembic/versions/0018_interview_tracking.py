"""Interview tracking: contact, source, rounds and questions per pipeline job (feature 002e).

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-12
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
NOW = sa.text("now()")


def _stamps() -> list[Any]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "job_pipeline_details",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("contact_name", sa.Text()),
        sa.Column("contact_role", sa.Text()),
        sa.Column("contact_email", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("contact_linkedin", sa.Text()),
        sa.Column("source", sa.Text()),
        sa.Column("firm_name", sa.Text()),
        *_stamps(),
        sa.PrimaryKeyConstraint("job_id", name="pk_job_pipeline_details"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{S}.jobs.id"],
            name="fk_job_pipeline_details_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "source IS NULL OR source IN ('direct', 'hiring_firm')",
            name="ck_job_pipeline_details_source_values",
        ),
        sa.CheckConstraint(
            "(source IS NOT DISTINCT FROM 'hiring_firm') = (firm_name IS NOT NULL)",
            name="ck_job_pipeline_details_firm_iff_hiring_firm",
        ),
        sa.CheckConstraint(
            "contact_name IS NOT NULL OR (contact_role IS NULL AND contact_email IS NULL"
            " AND contact_phone IS NULL AND contact_linkedin IS NULL)",
            name="ck_job_pipeline_details_contact_has_name",
        ),
        sa.CheckConstraint(
            "char_length(contact_name) BETWEEN 1 AND 120",
            name="ck_job_pipeline_details_contact_name_length",
        ),
        sa.CheckConstraint(
            "char_length(contact_role) <= 120", name="ck_job_pipeline_details_contact_role_length"
        ),
        sa.CheckConstraint(
            "char_length(contact_email) <= 254",
            name="ck_job_pipeline_details_contact_email_length",
        ),
        sa.CheckConstraint(
            "contact_phone IS NULL OR contact_phone ~ '^[0-9 +()-]{5,30}$'",
            name="ck_job_pipeline_details_contact_phone_shape",
        ),
        sa.CheckConstraint(
            "char_length(contact_linkedin) <= 500",
            name="ck_job_pipeline_details_contact_linkedin_length",
        ),
        sa.CheckConstraint(
            "char_length(firm_name) BETWEEN 1 AND 120",
            name="ck_job_pipeline_details_firm_name_length",
        ),
        schema=S,
    )

    op.create_table(
        "interview_rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("interviewers", sa.Text()),
        sa.Column("state", sa.Text(), server_default="scheduled", nullable=False),
        sa.Column("feedback", sa.Text()),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_interview_rounds"),
        sa.ForeignKeyConstraint(
            ["job_id"], [f"{S}.jobs.id"], name="fk_interview_rounds_job_id_jobs", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("job_id", "number", name="uq_interview_rounds_job_number"),
        sa.CheckConstraint(
            "kind IN ('screening', 'technical', 'hr', 'managerial', 'other')",
            name="ck_interview_rounds_kind_values",
        ),
        sa.CheckConstraint(
            "state IN ('scheduled', 'cleared', 'failed')", name="ck_interview_rounds_state_values"
        ),
        sa.CheckConstraint("number >= 1", name="ck_interview_rounds_number_positive"),
        sa.CheckConstraint(
            "char_length(interviewers) <= 300", name="ck_interview_rounds_interviewers_length"
        ),
        sa.CheckConstraint(
            "char_length(feedback) <= 10000", name="ck_interview_rounds_feedback_length"
        ),
        schema=S,
    )
    op.create_index("ix_app_interview_rounds_job_id", "interview_rounds", ["job_id"], schema=S)

    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_interview_questions"),
        sa.ForeignKeyConstraint(
            ["round_id"],
            [f"{S}.interview_rounds.id"],
            name="fk_interview_questions_round_id_interview_rounds",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("position >= 1", name="ck_interview_questions_position_positive"),
        sa.CheckConstraint(
            "char_length(question) BETWEEN 1 AND 2000",
            name="ck_interview_questions_question_length",
        ),
        sa.CheckConstraint(
            "char_length(answer) <= 10000", name="ck_interview_questions_answer_length"
        ),
        schema=S,
    )
    op.create_index(
        "ix_app_interview_questions_round_id", "interview_questions", ["round_id"], schema=S
    )


def downgrade() -> None:
    op.drop_table("interview_questions", schema=S)
    op.drop_table("interview_rounds", schema=S)
    op.drop_table("job_pipeline_details", schema=S)
