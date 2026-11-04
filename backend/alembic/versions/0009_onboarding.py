"""First-run setup: display name and setup-completed time (setup).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("display_name", sa.Text(), nullable=True), schema="app")
    op.add_column(
        "settings",
        sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.create_check_constraint(
        "ck_settings_display_name_length",
        "settings",
        "char_length(display_name) BETWEEN 1 AND 120",
        schema="app",
    )
    # An install that already has a confirmed profile and saved preferences counts as set up.
    op.execute(
        "UPDATE app.settings SET setup_completed_at = now() "
        "WHERE EXISTS (SELECT 1 FROM app.profiles WHERE current_version_id IS NOT NULL) "
        "AND EXISTS (SELECT 1 FROM app.preferences WHERE saved_at IS NOT NULL)"
    )


def downgrade() -> None:
    op.drop_constraint("ck_settings_display_name_length", "settings", schema="app", type_="check")
    op.drop_column("settings", "setup_completed_at", schema="app")
    op.drop_column("settings", "display_name", schema="app")
