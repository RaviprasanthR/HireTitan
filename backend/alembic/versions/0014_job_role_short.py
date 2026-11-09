"""A job can carry a short role given by the relevance step (the Applied table shows it).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("role_short", sa.Text(), nullable=True), schema="app")
    op.create_check_constraint(
        "ck_jobs_role_short_length",
        "jobs",
        "role_short IS NULL OR char_length(role_short) BETWEEN 1 AND 60",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint("ck_jobs_role_short_length", "jobs", schema="app", type_="check")
    op.drop_column("jobs", "role_short", schema="app")
