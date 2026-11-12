"""HireTitan has no AI budget and shows no AI cost (feature 002d).

A run the old budget had paused becomes a failed run with a plain message (the person can start
it again); then the budget and every cost column go.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
_PAUSE = "ck_workflow_runs_pause_reason_values"
BEFORE = "pause_reason IN ('key_missing', 'key_rejected', 'budget_reached', 'out_of_credit')"
AFTER = "pause_reason IN ('key_missing', 'key_rejected', 'out_of_credit')"
MESSAGE = "Paused by the old AI budget, which HireTitan no longer has. Start it again."


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE app.workflow_runs SET status = 'failed', pause_reason = NULL, error = :message "
            "WHERE status = 'paused' AND pause_reason = 'budget_reached'"
        ).bindparams(message=MESSAGE)
    )
    op.drop_constraint(_PAUSE, "workflow_runs", type_="check", schema=S)
    op.create_check_constraint(_PAUSE, "workflow_runs", AFTER, schema=S)
    op.drop_constraint("ck_settings_budget_cap_non_negative", "settings", type_="check", schema=S)
    op.drop_column("settings", "budget_cap_usd", schema=S)
    op.drop_column("llm_calls", "cost_usd", schema=S)
    op.drop_column("llm_calls", "estimated_cost_usd", schema=S)
    op.drop_column("search_runs", "ai_cost_usd", schema=S)


def downgrade() -> None:
    # The money columns come back empty: what was spent is not kept. Failed runs stay failed.
    op.add_column(
        "search_runs",
        sa.Column("ai_cost_usd", sa.Numeric(10, 4), server_default=sa.text("0"), nullable=False),
        schema=S,
    )
    op.add_column(
        "llm_calls",
        sa.Column(
            "estimated_cost_usd", sa.Numeric(10, 6), server_default=sa.text("0"), nullable=False
        ),
        schema=S,
    )
    op.add_column(
        "llm_calls",
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default=sa.text("0"), nullable=False),
        schema=S,
    )
    op.add_column(
        "settings",
        sa.Column(
            "budget_cap_usd", sa.Numeric(8, 2), server_default=sa.text("25.00"), nullable=False
        ),
        schema=S,
    )
    op.create_check_constraint(
        "ck_settings_budget_cap_non_negative", "settings", "budget_cap_usd >= 0", schema=S
    )
    op.drop_constraint(_PAUSE, "workflow_runs", type_="check", schema=S)
    op.create_check_constraint(_PAUSE, "workflow_runs", BEFORE, schema=S)
