"""Email as a third outreach draft kind (002m quick actions).

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
NAME = "ck_outreach_drafts_kind_values"


def _in(values: tuple[str, ...]) -> str:
    return "kind IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(NAME, "outreach_drafts", schema=S, type_="check")
    op.create_check_constraint(
        NAME,
        "outreach_drafts",
        _in(("connection_request", "referral_message", "email")),
        schema=S,
    )


def downgrade() -> None:
    op.execute("DELETE FROM app.outreach_drafts WHERE kind = 'email'")
    op.drop_constraint(NAME, "outreach_drafts", schema=S, type_="check")
    op.create_check_constraint(
        NAME, "outreach_drafts", _in(("connection_request", "referral_message")), schema=S
    )
