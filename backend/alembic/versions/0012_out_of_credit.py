"""A run can pause, and the provider status can say, that the AI account is out of credit (R7).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_workflow_runs_pause_reason_values"
_STATUS_NAME = "ck_provider_status_status_values"


def upgrade() -> None:
    op.drop_constraint(_STATUS_NAME, "provider_status", schema="app", type_="check")
    op.create_check_constraint(
        _STATUS_NAME,
        "provider_status",
        "status IN ('unknown', 'working', 'missing', 'rejected', 'unreachable', 'out_of_credit')",
        schema="app",
    )
    op.drop_constraint(_NAME, "workflow_runs", schema="app", type_="check")
    op.create_check_constraint(
        _NAME,
        "workflow_runs",
        "pause_reason IN ('key_missing', 'key_rejected', 'budget_reached', 'out_of_credit')",
        schema="app",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE app.provider_status SET status = 'unknown', message = NULL "
        "WHERE status = 'out_of_credit'"
    )
    op.drop_constraint(_STATUS_NAME, "provider_status", schema="app", type_="check")
    op.create_check_constraint(
        _STATUS_NAME,
        "provider_status",
        "status IN ('unknown', 'working', 'missing', 'rejected', 'unreachable')",
        schema="app",
    )
    op.execute(
        "UPDATE app.workflow_runs SET pause_reason = 'budget_reached' "
        "WHERE pause_reason = 'out_of_credit'"
    )
    op.drop_constraint(_NAME, "workflow_runs", schema="app", type_="check")
    op.create_check_constraint(
        _NAME,
        "workflow_runs",
        "pause_reason IN ('key_missing', 'key_rejected', 'budget_reached')",
        schema="app",
    )
