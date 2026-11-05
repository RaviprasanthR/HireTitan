"""Resume files can be marked as not a resume (profile).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_resume_files_parse_status_values"


def upgrade() -> None:
    op.drop_constraint(_NAME, "resume_files", schema="app", type_="check")
    op.create_check_constraint(
        _NAME,
        "resume_files",
        "parse_status IN ('pending', 'parsed', 'no_text', 'not_resume', 'failed')",
        schema="app",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE app.resume_files SET parse_status = 'no_text' WHERE parse_status = 'not_resume'"
    )
    op.drop_constraint(_NAME, "resume_files", schema="app", type_="check")
    op.create_check_constraint(
        _NAME,
        "resume_files",
        "parse_status IN ('pending', 'parsed', 'no_text', 'failed')",
        schema="app",
    )
