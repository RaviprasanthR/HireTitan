"""The inquired job state and its date (feature 002d).

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
BEFORE = "state IN ('explore', 'skipped', 'applied', 'deleted')"
AFTER = "state IN ('explore', 'skipped', 'inquired', 'applied', 'deleted')"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("inquired_on", sa.Date()), schema=S)
    op.drop_constraint("ck_jobs_state_values", "jobs", type_="check", schema=S)
    op.create_check_constraint("ck_jobs_state_values", "jobs", AFTER, schema=S)
    op.create_check_constraint(
        "ck_jobs_inquired_on_iff_inquired",
        "jobs",
        "(state = 'inquired') = (inquired_on IS NOT NULL)",
        schema=S,
    )


def downgrade() -> None:
    # An inquired job goes back to Explore, where the person can mark it again.
    op.execute("UPDATE app.jobs SET state = 'explore', inquired_on = NULL WHERE state = 'inquired'")
    op.drop_constraint("ck_jobs_inquired_on_iff_inquired", "jobs", type_="check", schema=S)
    op.drop_constraint("ck_jobs_state_values", "jobs", type_="check", schema=S)
    op.create_check_constraint("ck_jobs_state_values", "jobs", BEFORE, schema=S)
    op.drop_column("jobs", "inquired_on", schema=S)
