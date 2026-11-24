"""A pasted job post waiting in a chat before it is saved (002m quick flow).

A job in the hidden state ``staged`` is invisible everywhere; the person's yes makes it an Explore
job, their no deletes it. ``assistant_staged`` says which conversation is holding it.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
BEFORE = "state IN ('explore', 'skipped', 'inquired', 'applied', 'deleted')"
AFTER = "state IN ('explore', 'skipped', 'inquired', 'applied', 'deleted', 'staged')"
KINDS = "kind IN ('connection_request', 'referral_message', 'email')"


def upgrade() -> None:
    op.drop_constraint("ck_jobs_state_values", "jobs", type_="check", schema=S)
    op.create_check_constraint("ck_jobs_state_values", "jobs", AFTER, schema=S)
    op.create_table(
        "assistant_staged",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text()),
        sa.Column("job_id", sa.Uuid()),
        sa.Column("needs_details", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("conversation_id", name="pk_assistant_staged"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            [f"{S}.assistant_conversations.id"],
            name="fk_assistant_staged_conversation_id_assistant_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{S}.jobs.id"],
            name="fk_assistant_staged_job_id_jobs",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(KINDS, name="ck_assistant_staged_kind_values"),
        schema=S,
    )


def downgrade() -> None:
    op.drop_table("assistant_staged", schema=S)
    op.execute("DELETE FROM app.jobs WHERE state = 'staged'")
    op.drop_constraint("ck_jobs_state_values", "jobs", type_="check", schema=S)
    op.create_check_constraint("ck_jobs_state_values", "jobs", BEFORE, schema=S)
