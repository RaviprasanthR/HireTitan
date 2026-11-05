"""ORM model for ``app.workflow_runs`` (data-model.md)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import Base, IdTimestampMixin


class WorkflowRunRow(IdTimestampMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_review', 'paused', 'done', 'failed',"
            " 'cancelled')",
            name="status_values",
        ),
        CheckConstraint(
            "pause_reason IN ('key_missing', 'key_rejected', 'budget_reached')",
            name="pause_reason_values",
        ),
        CheckConstraint(
            "waiting_for IN ('profile_review', 'injection_decision')",
            name="waiting_for_values",
        ),
        CheckConstraint(
            "(status = 'paused') = (pause_reason IS NOT NULL)", name="pause_reason_iff_paused"
        ),
        CheckConstraint(
            "(status = 'awaiting_review') = (waiting_for IS NOT NULL)",
            name="waiting_for_iff_awaiting_review",
        ),
        Index("ix_workflow_runs_status", "status"),
    )

    # id doubles as the LangGraph thread_id
    workflow: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(Text)
    pause_reason: Mapped[str | None] = mapped_column(Text)
    waiting_for: Mapped[str | None] = mapped_column(Text)
    current_step: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
