"""Indexes on the drafts foreign keys and a byte-size check for tailored resumes (002k review).

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
# a deleted contact, run or profile version sets these to NULL; without an index that scans
INDEXES = (
    ("ix_outreach_drafts_recipient_contact_id", "outreach_drafts", "recipient_contact_id"),
    ("ix_outreach_drafts_run_id", "outreach_drafts", "run_id"),
    ("ix_tailored_resumes_run_id", "tailored_resumes", "run_id"),
    ("ix_tailored_resumes_profile_version_id", "tailored_resumes", "profile_version_id"),
)
SIZE = "ck_tailored_resumes_document_size"


def upgrade() -> None:
    for name, table, column in INDEXES:
        op.create_index(
            name,
            table,
            [column],
            schema=S,
            postgresql_where=f"{column} IS NOT NULL",
        )
    # pg_column_size is the stored (compressed) size, so a large document could pass
    op.drop_constraint(SIZE, "tailored_resumes", schema=S, type_="check")
    op.create_check_constraint(
        SIZE,
        "tailored_resumes",
        "document IS NULL OR octet_length(document::text) <= 65536",
        schema=S,
    )


def downgrade() -> None:
    op.drop_constraint(SIZE, "tailored_resumes", schema=S, type_="check")
    op.create_check_constraint(
        SIZE,
        "tailored_resumes",
        "document IS NULL OR pg_column_size(document) <= 65536",
        schema=S,
    )
    for name, table, _column in reversed(INDEXES):
        op.drop_index(name, table_name=table, schema=S)
