"""A saved profile version cannot be deleted row by row.

Versions were already immutable against UPDATE. This adds the same guard against DELETE, so a bug
or a stray query cannot drop one. "Delete all my data" empties the tables with TRUNCATE, which a
row trigger does not intercept, so it still works.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
CREATE FUNCTION app.profile_versions_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'profile versions are immutable';
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute(_FUNCTION)
    op.execute(
        "CREATE TRIGGER profile_versions_no_delete BEFORE DELETE ON app.profile_versions "
        "FOR EACH ROW EXECUTE FUNCTION app.profile_versions_no_delete()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER profile_versions_no_delete ON app.profile_versions")
    op.execute("DROP FUNCTION app.profile_versions_no_delete()")
