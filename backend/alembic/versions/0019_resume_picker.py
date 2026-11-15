"""Resume picker: the resume used for a pipeline job, and the person's last choice (feature 002f).

Three columns on ``job_pipeline_details`` (the link to the stored file, and a copy of its name and
the day it was added) and a one-row ``pipeline_settings`` table. Both links are ``ON DELETE SET
NULL``: removing a resume file clears the link and leaves the copied name behind as a note.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
T = "job_pipeline_details"
FK = "fk_job_pipeline_details_resume_file_id_resume_files"
IX = "ix_job_pipeline_details_resume_file_id"
CHECKS = {
    "ck_job_pipeline_details_resume_name_length": "char_length(resume_name) BETWEEN 1 AND 255",
    "ck_job_pipeline_details_resume_snapshot_together": (
        "(resume_name IS NULL) = (resume_added_on IS NULL)"
    ),
    "ck_job_pipeline_details_resume_link_has_snapshot": (
        "resume_file_id IS NULL OR resume_name IS NOT NULL"
    ),
}


def upgrade() -> None:
    op.add_column(T, sa.Column("resume_file_id", sa.Uuid()), schema=S)
    op.add_column(T, sa.Column("resume_name", sa.Text()), schema=S)
    op.add_column(T, sa.Column("resume_added_on", sa.Date()), schema=S)
    op.create_foreign_key(
        FK, T, "resume_files", ["resume_file_id"], ["id"],
        source_schema=S, referent_schema=S, ondelete="SET NULL",
    )  # fmt: skip
    for name, expression in CHECKS.items():
        op.create_check_constraint(name, T, expression, schema=S)
    op.create_index(IX, T, ["resume_file_id"], schema=S)

    op.create_table(
        "pipeline_settings",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("last_resume_file_id", sa.Uuid()),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_settings"),
        sa.ForeignKeyConstraint(
            ["last_resume_file_id"],
            [f"{S}.resume_files.id"],
            name="fk_pipeline_settings_last_resume_file_id_resume_files",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("id = 1", name="ck_pipeline_settings_single_row"),
        schema=S,
    )


def downgrade() -> None:
    op.drop_table("pipeline_settings", schema=S)
    op.drop_index(IX, table_name=T, schema=S)
    for name in CHECKS:
        op.drop_constraint(name, T, schema=S, type_="check")
    op.drop_constraint(FK, T, schema=S, type_="foreignkey")
    op.drop_column(T, "resume_added_on", schema=S)
    op.drop_column(T, "resume_name", schema=S)
    op.drop_column(T, "resume_file_id", schema=S)
