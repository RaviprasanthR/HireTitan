"""Provider status (platform/llm).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_status",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("provider", name="pk_provider_status"),
        sa.CheckConstraint(
            "status IN ('unknown', 'working', 'missing', 'rejected', 'unreachable')",
            name="ck_provider_status_status_values",
        ),
        schema="app",
    )
    op.execute("INSERT INTO app.provider_status (provider, status) VALUES ('openai', 'unknown')")


def downgrade() -> None:
    op.drop_table("provider_status", schema="app")
