"""Profile tables (profile module): resume files, reviews, profiles and versions.

Reviews and versions point at each other, so the tables are created first and the two
back-references are added afterwards. A trigger keeps a version immutable.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.func.now()

_GUARD_FUNCTION = """
CREATE FUNCTION app.profile_versions_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.profile_id IS DISTINCT FROM OLD.profile_id
       OR NEW.number IS DISTINCT FROM OLD.number
       OR NEW.content IS DISTINCT FROM OLD.content
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.prompt_name IS DISTINCT FROM OLD.prompt_name
       OR NEW.prompt_version IS DISTINCT FROM OLD.prompt_version
       OR NEW.provider IS DISTINCT FROM OLD.provider
       OR NEW.model IS DISTINCT FROM OLD.model
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR (NEW.source_file_id IS NOT NULL
           AND NEW.source_file_id IS DISTINCT FROM OLD.source_file_id)
       OR (NEW.review_id IS NOT NULL AND NEW.review_id IS DISTINCT FROM OLD.review_id)
       OR (OLD.source_deleted AND NOT NEW.source_deleted)
    THEN
        RAISE EXCEPTION 'profile versions are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.create_table(
        "resume_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("parse_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_resume_files"),
        sa.CheckConstraint(
            "kind IN ('upload_pdf', 'upload_docx', 'pasted_text')",
            name="ck_resume_files_kind_values",
        ),
        sa.CheckConstraint(
            "char_length(original_name) <= 255", name="ck_resume_files_original_name_length"
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 5242880", name="ck_resume_files_size_bytes_range"
        ),
        sa.CheckConstraint("char_length(sha256) = 64", name="ck_resume_files_sha256_length"),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count BETWEEN 1 AND 20",
            name="ck_resume_files_page_count_range",
        ),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'parsed', 'no_text', 'failed')",
            name="ck_resume_files_parse_status_values",
        ),
        schema="app",
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("singleton", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profiles"),
        sa.UniqueConstraint("singleton", name="uq_profiles_singleton"),
        sa.CheckConstraint("singleton", name="ck_profiles_singleton"),
        schema="app",
    )
    op.create_table(
        "profile_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("resume_file_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dropped_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("compare_to_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "changed_paths",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("draft_saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profile_reviews"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["app.workflow_runs.id"], name="fk_profile_reviews_run_id_workflow_runs"
        ),
        sa.ForeignKeyConstraint(
            ["resume_file_id"],
            ["app.resume_files.id"],
            name="fk_profile_reviews_resume_file_id_resume_files",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", name="uq_profile_reviews_run_id"),
        sa.CheckConstraint(
            "status IN ('open', 'confirmed', 'discarded')", name="ck_profile_reviews_status_values"
        ),
        schema="app",
    )
    op.create_index(
        "uq_profile_reviews_one_open",
        "profile_reviews",
        ["status"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "profile_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=True),
        sa.Column("source_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profile_versions"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["app.profiles.id"], name="fk_profile_versions_profile_id_profiles"
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["app.resume_files.id"],
            name="fk_profile_versions_source_file_id_resume_files",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("profile_id", "number", name="uq_profile_versions_profile_id_number"),
        sa.CheckConstraint(
            "created_by IN ('extraction', 'manual', 'manual_edit')",
            name="ck_profile_versions_created_by_values",
        ),
        schema="app",
    )
    # The back-references, now that both sides exist.
    op.create_foreign_key(
        "fk_profile_versions_review_id_profile_reviews",
        "profile_versions",
        "profile_reviews",
        ["review_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_profile_reviews_compare_to_version_id_profile_versions",
        "profile_reviews",
        "profile_versions",
        ["compare_to_version_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
    )
    op.create_foreign_key(
        "fk_profiles_current_version_id_profile_versions",
        "profiles",
        "profile_versions",
        ["current_version_id"],
        ["id"],
        source_schema="app",
        referent_schema="app",
    )
    op.execute(_GUARD_FUNCTION)
    op.execute(
        "CREATE TRIGGER profile_versions_immutable BEFORE UPDATE ON app.profile_versions "
        "FOR EACH ROW EXECUTE FUNCTION app.profile_versions_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER profile_versions_immutable ON app.profile_versions")
    op.execute("DROP FUNCTION app.profile_versions_guard()")
    op.drop_constraint(
        "fk_profiles_current_version_id_profile_versions",
        "profiles",
        schema="app",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_profile_reviews_compare_to_version_id_profile_versions",
        "profile_reviews",
        schema="app",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_profile_versions_review_id_profile_reviews",
        "profile_versions",
        schema="app",
        type_="foreignkey",
    )
    op.drop_table("profile_versions", schema="app")
    op.drop_index("uq_profile_reviews_one_open", table_name="profile_reviews", schema="app")
    op.drop_table("profile_reviews", schema="app")
    op.drop_table("profiles", schema="app")
    op.drop_table("resume_files", schema="app")
