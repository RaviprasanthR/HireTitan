"""Settings singleton (setup).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "budget_cap_usd", sa.Numeric(8, 2), server_default=sa.text("25.00"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_settings"),
        sa.CheckConstraint("id", name="ck_settings_singleton"),
        sa.CheckConstraint("budget_cap_usd >= 0", name="ck_settings_budget_cap_non_negative"),
        schema="app",
    )
    op.execute("INSERT INTO app.settings DEFAULT VALUES")


def downgrade() -> None:
    op.drop_table("settings", schema="app")
