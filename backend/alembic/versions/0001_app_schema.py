"""Baseline: schema ``app`` for HireTitan's tables.

Revision ID: 0001
Revises:
Create Date: 2026-11-04

Downgrade leaves the schema in place: it also holds Alembic's own version table
(``app.alembic_version``), which Alembic still needs while downgrading. Later
migrations drop their own tables on downgrade.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")


def downgrade() -> None:
    pass
