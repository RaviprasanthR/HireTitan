"""LLM call log (platform/llm).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("prompt_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_calls"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["app.workflow_runs.id"],
            name="fk_llm_calls_run_id_workflow_runs",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "outcome IN ('ok', 'repaired', 'fallback', 'refused', 'budget_blocked',"
            " 'key_rejected', 'error')",
            name="ck_llm_calls_outcome_values",
        ),
        schema="app",
    )
    op.create_index("ix_llm_calls_created_at", "llm_calls", ["created_at"], schema="app")


def downgrade() -> None:
    op.drop_index("ix_llm_calls_created_at", table_name="llm_calls", schema="app")
    op.drop_table("llm_calls", schema="app")
