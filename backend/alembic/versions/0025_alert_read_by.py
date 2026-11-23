"""Who gave an alert job's company and place: a site's fixed reader or the AI (FR-013d).

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("alert_read_by", sa.Text()), schema=S)
    op.create_check_constraint(
        "ck_jobs_alert_read_by_values",
        "jobs",
        "alert_read_by IS NULL OR alert_read_by IN ('fixed', 'ai')",
        schema=S,
    )


def downgrade() -> None:
    op.drop_constraint("ck_jobs_alert_read_by_values", "jobs", schema=S, type_="check")
    op.drop_column("jobs", "alert_read_by", schema=S)
