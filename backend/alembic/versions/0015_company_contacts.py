"""Company contacts and one note per company (feature 002b).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-09
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
NOW = sa.text("now()")


def _stamps() -> list[Any]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def _company_fk(name: str) -> Any:
    return sa.ForeignKeyConstraint(
        ["company_id"], [f"{S}.companies.id"], name=name, ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "company_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("role", sa.Text()),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("link_key", sa.Text()),
        sa.Column("email", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("confidence", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_company_contacts"),
        _company_fk("fk_company_contacts_company_id_companies"),
        sa.UniqueConstraint("company_id", "name_key", name="uq_company_contacts_company_name"),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'medium', 'low')",
            name="ck_company_contacts_confidence",
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name="ck_company_contacts_name_length"
        ),
        sa.CheckConstraint(
            "char_length(name_key) BETWEEN 1 AND 120",
            name="ck_company_contacts_name_key_not_empty",
        ),
        sa.CheckConstraint("char_length(role) <= 120", name="ck_company_contacts_role_length"),
        sa.CheckConstraint(
            "char_length(linkedin_url) <= 500", name="ck_company_contacts_linkedin_url_length"
        ),
        sa.CheckConstraint("char_length(email) <= 254", name="ck_company_contacts_email_length"),
        sa.CheckConstraint(
            "phone IS NULL OR phone ~ '^[0-9 +()-]{5,30}$'",
            name="ck_company_contacts_phone_shape",
        ),
        sa.CheckConstraint("char_length(note) <= 2000", name="ck_company_contacts_note_length"),
        sa.CheckConstraint(
            "source IN ('import', 'typed')", name="ck_company_contacts_source_values"
        ),
        schema=S,
    )
    op.create_index(
        "ix_company_contacts_company_link",
        "company_contacts",
        ["company_id", "link_key"],
        schema=S,
        postgresql_where=sa.text("link_key IS NOT NULL"),
    )
    op.create_table(
        "company_notes",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("company_id", name="pk_company_notes"),
        _company_fk("fk_company_notes_company_id_companies"),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 5000", name="ck_company_notes_body_length"
        ),
        sa.CheckConstraint("source IN ('import', 'typed')", name="ck_company_notes_source_values"),
        schema=S,
    )


def downgrade() -> None:
    op.drop_table("company_notes", schema=S)
    op.drop_index("ix_company_contacts_company_link", table_name="company_contacts", schema=S)
    op.drop_table("company_contacts", schema=S)
