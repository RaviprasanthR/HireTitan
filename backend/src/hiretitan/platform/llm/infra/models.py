"""ORM model for ``app.llm_calls`` (data-model.md). Never stores prompt or response text."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import APP_SCHEMA, Base, uuid7

OUTCOMES = (
    "ok",
    "repaired",
    "fallback",
    "refused",
    "budget_blocked",
    "key_rejected",
    "error",
)


class LlmCallRow(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint(
            "outcome IN (" + ", ".join(f"'{o}'" for o in OUTCOMES) + ")", name="outcome_values"
        ),
        Index("ix_llm_calls_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.workflow_runs.id", ondelete="SET NULL")
    )
    task: Mapped[str] = mapped_column(Text)
    prompt_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int]
    cached_input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int]
    outcome: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


STATUSES = ("unknown", "working", "missing", "rejected", "unreachable", "out_of_credit")


class ProviderStatusRow(Base):
    """``app.provider_status``: one row per provider; the message never contains a key."""

    __tablename__ = "provider_status"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")", name="status_values"
        ),
    )

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
