"""ORM models for the search module's tables (data-model.md, migration 0013).

The database repeats every rule from the data model as a named constraint, so a repository bug
cannot store a value the model forbids.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import APP_SCHEMA, Base, IdTimestampMixin
from hiretitan.search.domain.companies import CHECK_RESULTS, COMPANY_ORIGINS, RESOLUTIONS

JsonDict = dict[str, Any]


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


RULE_SET_STATUSES = ("proposed", "approved", "superseded")
RUN_MODES = ("rules_and_ai", "rules_only")
RUN_OUTCOMES = ("finished", "stopped_by_user", "budget_reached", "out_of_credit", "failed")
JOB_STATES = ("explore", "skipped", "applied", "deleted")
WORK_MODES = ("onsite", "hybrid", "remote")
SOURCE_KINDS = ("company_board", "careers_page", "paste")
DECISION_OUTCOMES = ("shown", "skipped")
DECIDED_BY = ("rule", "ai", "person", "rules_only_fallback")
DUPLICATE_STATUSES = ("open", "merged", "dismissed")


class CompanyRow(IdTimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("key"),  # several rows without a key are allowed (NULLs differ)
        CheckConstraint(_in("origin", COMPANY_ORIGINS), name="origin_values"),
        CheckConstraint(_in("resolution", RESOLUTIONS), name="resolution_values"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("char_length(city) <= 80", name="city_length"),
        CheckConstraint("char_length(website) <= 500", name="website_length"),
        CheckConstraint("char_length(careers_url) <= 500", name="careers_url_length"),
        CheckConstraint("char_length(board_id) <= 200", name="board_id_length"),
        CheckConstraint("ats_vendor IS NULL OR board_id IS NOT NULL", name="vendor_needs_board_id"),
        CheckConstraint(
            "last_check_result IS NULL OR " + _in("last_check_result", CHECK_RESULTS),
            name="last_check_result_values",
        ),
        CheckConstraint("char_length(last_check_error) <= 300", name="last_check_error_length"),
    )

    key: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    careers_url: Mapped[str | None] = mapped_column(Text)
    ats_vendor: Mapped[str | None] = mapped_column(Text)
    board_id: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    user_modified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seed_version: Mapped[int | None] = mapped_column(Integer)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_result: Mapped[str | None] = mapped_column(Text)
    last_check_error: Mapped[str | None] = mapped_column(Text)


class SearchRuleSetRow(IdTimestampMixin, Base):
    __tablename__ = "search_rule_sets"
    __table_args__ = (
        UniqueConstraint("version"),
        CheckConstraint(_in("status", RULE_SET_STATUSES), name="status_values"),
        # at most one approved set at a time
        Index(
            "uq_search_rule_sets_one_approved",
            "status",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
    )

    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    rules: Mapped[JsonDict] = mapped_column(JSONB)
    based_on: Mapped[JsonDict] = mapped_column(JSONB)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchRunRow(IdTimestampMixin, Base):
    __tablename__ = "search_runs"
    __table_args__ = (
        UniqueConstraint("workflow_run_id"),
        CheckConstraint(_in("mode", RUN_MODES), name="mode_values"),
        CheckConstraint(
            "outcome IS NULL OR " + _in("outcome", RUN_OUTCOMES), name="outcome_values"
        ),
        CheckConstraint("char_length(stop_message) <= 300", name="stop_message_length"),
    )

    workflow_run_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.workflow_runs.id"))
    rule_set_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.search_rule_sets.id"))
    mode: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    stop_message: Mapped[str | None] = mapped_column(Text)
    company_order: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))
    next_index: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    stop_requested: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    batches_done: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    jobs_found: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    skipped_by_rules: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    judged_by_ai: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    kept: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    added: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    merged: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    not_checked_by_ai: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    ai_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), server_default=text("0"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchRunCompanyRow(Base):
    __tablename__ = "search_run_companies"
    __table_args__ = (
        PrimaryKeyConstraint("search_run_id", "company_id", name="pk_search_run_companies"),
        CheckConstraint(_in("result", CHECK_RESULTS), name="result_values"),
        CheckConstraint("char_length(error) <= 300", name="error_length"),
    )

    search_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.search_runs.id", ondelete="CASCADE")
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.companies.id", ondelete="CASCADE")
    )
    batch_no: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(Text)
    jobs_found: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)


class JobRow(IdTimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("canonical_url"),
        UniqueConstraint("ats_vendor", "requisition_id"),  # only binds when both are set
        CheckConstraint("char_length(company_name) BETWEEN 1 AND 120", name="company_name_length"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="title_length"),
        CheckConstraint(
            "role_short IS NULL OR char_length(role_short) BETWEEN 1 AND 60",
            name="role_short_length",
        ),
        CheckConstraint("char_length(location_text) <= 200", name="location_text_length"),
        CheckConstraint(
            "work_mode IS NULL OR " + _in("work_mode", WORK_MODES), name="work_mode_values"
        ),
        CheckConstraint("char_length(description) <= 30000", name="description_length"),
        CheckConstraint(_in("state", JOB_STATES), name="state_values"),
        CheckConstraint(
            "(state = 'applied') = (applied_on IS NOT NULL)", name="applied_on_iff_applied"
        ),
        Index("ix_jobs_state_sort", "state", text("sort_key DESC"), "id"),
        Index("ix_jobs_company", "company_id"),
    )

    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.companies.id", ondelete="SET NULL")
    )
    company_name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    role_short: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    work_mode: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sort_key: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        Computed("coalesce(posted_at, first_seen_at)", persisted=True),
    )
    description: Mapped[str] = mapped_column(Text)
    pay_text: Mapped[str | None] = mapped_column(Text)
    skills_found: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    years_found: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    canonical_url: Mapped[str | None] = mapped_column(Text)
    ats_vendor: Mapped[str | None] = mapped_column(Text)
    requisition_id: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    restored: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    applied_on: Mapped[date | None] = mapped_column(Date)
    listed: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    injection_flags: Mapped[list[JsonDict]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )


class JobSourceRow(IdTimestampMixin, Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("job_id", "kind", "url"),
        CheckConstraint(_in("kind", SOURCE_KINDS), name="kind_values"),
        CheckConstraint("char_length(url) <= 1000", name="url_length"),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    search_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.search_runs.id", ondelete="SET NULL")
    )
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RelevanceDecisionRow(IdTimestampMixin, Base):
    __tablename__ = "relevance_decisions"
    __table_args__ = (
        CheckConstraint(_in("outcome", DECISION_OUTCOMES), name="outcome_values"),
        CheckConstraint(_in("decided_by", DECIDED_BY), name="decided_by_values"),
        CheckConstraint("char_length(reason) BETWEEN 1 AND 200", name="reason_length"),
        # history is kept, but exactly one decision per job is the current one
        Index(
            "uq_relevance_decisions_one_current",
            "job_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    job_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="CASCADE"))
    outcome: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    rule_key: Mapped[str | None] = mapped_column(Text)
    search_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.search_runs.id", ondelete="SET NULL")
    )
    prompt_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    llm_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.llm_calls.id", ondelete="SET NULL")
    )
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class PossibleDuplicateRow(IdTimestampMixin, Base):
    __tablename__ = "possible_duplicates"
    __table_args__ = (
        UniqueConstraint("job_a_id", "job_b_id"),
        CheckConstraint("job_a_id < job_b_id", name="ordered_pair"),
        CheckConstraint(_in("status", DUPLICATE_STATUSES), name="status_values"),
    )

    job_a_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="CASCADE"))
    job_b_id: Mapped[UUID] = mapped_column(ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="CASCADE"))
    similarity: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
