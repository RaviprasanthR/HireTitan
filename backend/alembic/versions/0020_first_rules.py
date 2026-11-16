"""Who approved a rule set (feature 002i).

``search_rule_sets.approved_by`` says whether the person approved a rule set (``person``) or
HireTitan approved the first one for them when setup finished (``auto``). Every approval made
before this migration was the person's, so those rows are backfilled with ``person``. A proposal
has no approver.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
T = "search_rule_sets"
CHECK = "ck_search_rule_sets_approved_by_values"


def upgrade() -> None:
    op.add_column(T, sa.Column("approved_by", sa.Text()), schema=S)
    op.execute(
        "UPDATE app.search_rule_sets SET approved_by = 'person' WHERE approved_at IS NOT NULL"
    )
    op.create_check_constraint(
        CHECK, T, "approved_by IS NULL OR approved_by IN ('person', 'auto')", schema=S
    )


def downgrade() -> None:
    op.drop_constraint(CHECK, T, schema=S, type_="check")
    op.drop_column(T, "approved_by", schema=S)
