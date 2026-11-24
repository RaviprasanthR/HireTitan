"""What a change of Mikasa's did, in words, so the chat history can show it (002m).

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"


def upgrade() -> None:
    op.add_column("assistant_changes", sa.Column("summary", sa.Text()), schema=S)
    op.create_check_constraint(
        "ck_assistant_changes_summary_length",
        "assistant_changes",
        "char_length(summary) <= 2000",
        schema=S,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_assistant_changes_summary_length", "assistant_changes", schema=S, type_="check"
    )
    op.drop_column("assistant_changes", "summary", schema=S)
