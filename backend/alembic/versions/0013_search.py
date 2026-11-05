"""Job search: companies, rule sets, search runs, jobs, sources, decisions, duplicates.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-05
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
NOW = sa.text("now()")
FALSE = sa.text("false")
ZERO = sa.text("0")


def _in(column: str, *values: str) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _stamps() -> list[Any]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def _fk(column: str, target: str, name: str, ondelete: str | None = None) -> Any:
    return sa.ForeignKeyConstraint([column], [f"{S}.{target}.id"], name=name, ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text()),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text()),
        sa.Column("website", sa.Text()),
        sa.Column("careers_url", sa.Text()),
        sa.Column("ats_vendor", sa.Text()),
        sa.Column("board_id", sa.Text()),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("user_modified", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("seed_version", sa.Integer()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_check_result", sa.Text()),
        sa.Column("last_check_error", sa.Text()),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
        sa.UniqueConstraint("key", name="uq_companies_key"),
        sa.CheckConstraint(_in("origin", "built_in", "user"), name="ck_companies_origin_values"),
        sa.CheckConstraint(
            _in(
                "resolution",
                "verified",
                "user_confirmed",
                "unresolved",
                "careers_page",
                "check_manually",
            ),
            name="ck_companies_resolution_values",
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="ck_companies_name_length"),
        sa.CheckConstraint("char_length(city) <= 80", name="ck_companies_city_length"),
        sa.CheckConstraint("char_length(website) <= 500", name="ck_companies_website_length"),
        sa.CheckConstraint(
            "char_length(careers_url) <= 500", name="ck_companies_careers_url_length"
        ),
        sa.CheckConstraint("char_length(board_id) <= 200", name="ck_companies_board_id_length"),
        sa.CheckConstraint(
            "ats_vendor IS NULL OR board_id IS NOT NULL", name="ck_companies_vendor_needs_board_id"
        ),
        sa.CheckConstraint(
            "last_check_result IS NULL OR "
            + _in("last_check_result", "ok", "failed", "no_jobs", "blocked", "unreadable"),
            name="ck_companies_last_check_result_values",
        ),
        sa.CheckConstraint(
            "char_length(last_check_error) <= 300", name="ck_companies_last_check_error_length"
        ),
        schema=S,
    )

    op.create_table(
        "search_rule_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("based_on", postgresql.JSONB(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_search_rule_sets"),
        sa.UniqueConstraint("version", name="uq_search_rule_sets_version"),
        sa.CheckConstraint(
            _in("status", "proposed", "approved", "superseded"),
            name="ck_search_rule_sets_status_values",
        ),
        schema=S,
    )
    op.create_index(
        "uq_search_rule_sets_one_approved",
        "search_rule_sets",
        ["status"],
        unique=True,
        schema=S,
        postgresql_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "search_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text()),
        sa.Column("stop_message", sa.Text()),
        sa.Column("company_order", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("next_index", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("stop_requested", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("batches_done", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("jobs_found", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("skipped_by_rules", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("judged_by_ai", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("kept", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("added", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("merged", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("not_checked_by_ai", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("ai_cost_usd", sa.Numeric(10, 4), server_default=ZERO, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_search_runs"),
        sa.UniqueConstraint("workflow_run_id", name="uq_search_runs_workflow_run_id"),
        _fk("workflow_run_id", "workflow_runs", "fk_search_runs_workflow_run_id_workflow_runs"),
        _fk("rule_set_id", "search_rule_sets", "fk_search_runs_rule_set_id_search_rule_sets"),
        sa.CheckConstraint(
            _in("mode", "rules_and_ai", "rules_only"), name="ck_search_runs_mode_values"
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR "
            + _in(
                "outcome",
                "finished",
                "stopped_by_user",
                "budget_reached",
                "out_of_credit",
                "failed",
            ),
            name="ck_search_runs_outcome_values",
        ),
        sa.CheckConstraint(
            "char_length(stop_message) <= 300", name="ck_search_runs_stop_message_length"
        ),
        schema=S,
    )

    op.create_table(
        "search_run_companies",
        sa.Column("search_run_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("batch_no", sa.Integer(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("jobs_found", sa.Integer(), server_default=ZERO, nullable=False),
        sa.Column("error", sa.Text()),
        sa.PrimaryKeyConstraint("search_run_id", "company_id", name="pk_search_run_companies"),
        _fk(
            "search_run_id",
            "search_runs",
            "fk_search_run_companies_search_run_id_search_runs",
            "CASCADE",
        ),
        _fk("company_id", "companies", "fk_search_run_companies_company_id_companies", "CASCADE"),
        sa.CheckConstraint(
            _in("result", "ok", "failed", "no_jobs", "blocked", "unreadable"),
            name="ck_search_run_companies_result_values",
        ),
        sa.CheckConstraint(
            "char_length(error) <= 300", name="ck_search_run_companies_error_length"
        ),
        schema=S,
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid()),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("location_text", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("work_mode", sa.Text()),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sort_key",
            sa.DateTime(timezone=True),
            sa.Computed("coalesce(posted_at, first_seen_at)", persisted=True),
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("pay_text", sa.Text()),
        sa.Column(
            "skills_found",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("years_found", sa.Numeric(4, 1)),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("ats_vendor", sa.Text()),
        sa.Column("requisition_id", sa.Text()),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("restored", sa.Boolean(), server_default=FALSE, nullable=False),
        sa.Column("applied_on", sa.Date()),
        sa.Column("listed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "injection_flags",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("canonical_url", name="uq_jobs_canonical_url"),
        sa.UniqueConstraint("ats_vendor", "requisition_id", name="uq_jobs_ats_vendor"),
        _fk("company_id", "companies", "fk_jobs_company_id_companies", "SET NULL"),
        sa.CheckConstraint(
            "char_length(company_name) BETWEEN 1 AND 120", name="ck_jobs_company_name_length"
        ),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_jobs_title_length"),
        sa.CheckConstraint(
            "char_length(location_text) <= 200", name="ck_jobs_location_text_length"
        ),
        sa.CheckConstraint(
            "work_mode IS NULL OR " + _in("work_mode", "onsite", "hybrid", "remote"),
            name="ck_jobs_work_mode_values",
        ),
        sa.CheckConstraint("char_length(description) <= 30000", name="ck_jobs_description_length"),
        sa.CheckConstraint(
            _in("state", "explore", "skipped", "applied", "deleted"), name="ck_jobs_state_values"
        ),
        sa.CheckConstraint(
            "(state = 'applied') = (applied_on IS NOT NULL)", name="ck_jobs_applied_on_iff_applied"
        ),
        schema=S,
    )
    op.create_index(
        "ix_jobs_state_sort", "jobs", ["state", sa.text("sort_key DESC"), "id"], schema=S
    )
    op.create_index("ix_jobs_company", "jobs", ["company_id"], schema=S)

    op.create_table(
        "job_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("search_run_id", sa.Uuid()),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_job_sources"),
        sa.UniqueConstraint("job_id", "kind", "url", name="uq_job_sources_job_id"),
        _fk("job_id", "jobs", "fk_job_sources_job_id_jobs", "CASCADE"),
        _fk("search_run_id", "search_runs", "fk_job_sources_search_run_id_search_runs", "SET NULL"),
        sa.CheckConstraint(
            _in("kind", "company_board", "careers_page", "paste"), name="ck_job_sources_kind_values"
        ),
        sa.CheckConstraint("char_length(url) <= 1000", name="ck_job_sources_url_length"),
        schema=S,
    )

    op.create_table(
        "relevance_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rule_key", sa.Text()),
        sa.Column("search_run_id", sa.Uuid()),
        sa.Column("prompt_name", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("provider", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("llm_call_id", sa.Uuid()),
        sa.Column("is_current", sa.Boolean(), server_default=FALSE, nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_relevance_decisions"),
        _fk("job_id", "jobs", "fk_relevance_decisions_job_id_jobs", "CASCADE"),
        _fk(
            "search_run_id",
            "search_runs",
            "fk_relevance_decisions_search_run_id_search_runs",
            "SET NULL",
        ),
        _fk("llm_call_id", "llm_calls", "fk_relevance_decisions_llm_call_id_llm_calls", "SET NULL"),
        sa.CheckConstraint(
            _in("outcome", "shown", "skipped"), name="ck_relevance_decisions_outcome_values"
        ),
        sa.CheckConstraint(
            _in("decided_by", "rule", "ai", "person", "rules_only_fallback"),
            name="ck_relevance_decisions_decided_by_values",
        ),
        sa.CheckConstraint(
            "char_length(reason) BETWEEN 1 AND 200", name="ck_relevance_decisions_reason_length"
        ),
        schema=S,
    )
    op.create_index(
        "uq_relevance_decisions_one_current",
        "relevance_decisions",
        ["job_id"],
        unique=True,
        schema=S,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "possible_duplicates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_a_id", sa.Uuid(), nullable=False),
        sa.Column("job_b_id", sa.Uuid(), nullable=False),
        sa.Column("similarity", sa.Numeric(5, 2), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        *_stamps(),
        sa.PrimaryKeyConstraint("id", name="pk_possible_duplicates"),
        sa.UniqueConstraint("job_a_id", "job_b_id", name="uq_possible_duplicates_job_a_id"),
        _fk("job_a_id", "jobs", "fk_possible_duplicates_job_a_id_jobs", "CASCADE"),
        _fk("job_b_id", "jobs", "fk_possible_duplicates_job_b_id_jobs", "CASCADE"),
        sa.CheckConstraint("job_a_id < job_b_id", name="ck_possible_duplicates_ordered_pair"),
        sa.CheckConstraint(
            _in("status", "open", "merged", "dismissed"),
            name="ck_possible_duplicates_status_values",
        ),
        schema=S,
    )

    # one job search at a time (FR-009)
    op.create_index(
        "uq_workflow_runs_one_active_job_search",
        "workflow_runs",
        ["workflow"],
        unique=True,
        schema=S,
        postgresql_where=sa.text(
            "workflow = 'job_search' AND status IN ('queued', 'running', 'paused')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_runs_one_active_job_search", table_name="workflow_runs", schema=S)
    for table in (
        "possible_duplicates",
        "relevance_decisions",
        "job_sources",
        "jobs",
        "search_run_companies",
        "search_runs",
        "search_rule_sets",
        "companies",
    ):
        op.drop_table(table, schema=S)
