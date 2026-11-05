"""Workflow runs (platform/runtime).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("waiting_for", sa.Text(), nullable=True),
        sa.Column("current_step", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_review', 'paused', 'done', 'failed',"
            " 'cancelled')",
            name="ck_workflow_runs_status_values",
        ),
        sa.CheckConstraint(
            "pause_reason IN ('key_missing', 'key_rejected', 'budget_reached')",
            name="ck_workflow_runs_pause_reason_values",
        ),
        sa.CheckConstraint(
            "waiting_for IN ('profile_review', 'injection_decision')",
            name="ck_workflow_runs_waiting_for_values",
        ),
        sa.CheckConstraint(
            "(status = 'paused') = (pause_reason IS NOT NULL)",
            name="ck_workflow_runs_pause_reason_iff_paused",
        ),
        sa.CheckConstraint(
            "(status = 'awaiting_review') = (waiting_for IS NOT NULL)",
            name="ck_workflow_runs_waiting_for_iff_awaiting_review",
        ),
        schema="app",
    )
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"], schema="app")


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs", schema="app")
    op.drop_table("workflow_runs", schema="app")
