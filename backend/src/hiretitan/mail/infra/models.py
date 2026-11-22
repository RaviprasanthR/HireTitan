"""Mail tables (feature 002c, data-model.md): the connection, the sender list, the read-once
registry and one row per mail check. No email body, subject or snippet is ever stored (FR-016)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.mail.domain.senders import SITES
from hiretitan.platform.db import APP_SCHEMA, Base, IdTimestampMixin

CONNECTION_STATES = ("connected", "needs_reconnect")
PURPOSES = ("job_alert",)
READ_OUTCOMES = ("read", "no_jobs", "unreadable", "needs_ai")
CHECK_TRIGGERS = ("daily", "button", "search_now")
CHECK_ENDINGS = ("finished", "stopped", "access_ended", "gmail_unavailable", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class MailConnectionRow(IdTimestampMixin, Base):
    """The person's link to their mailbox. One row at most; no row means not connected."""

    __tablename__ = "mail_connection"
    __table_args__ = (
        UniqueConstraint("provider"),
        CheckConstraint(_in("provider", ("gmail",)), name="provider_values"),
        CheckConstraint(_in("state", CONNECTION_STATES), name="state_values"),
        CheckConstraint("char_length(address) BETWEEN 3 AND 320", name="address_length"),
        CheckConstraint("char_length(last_error) <= 300", name="last_error_length"),
    )

    provider: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_check_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class MailSenderRow(IdTimestampMixin, Base):
    """A sender address that counts as a mail source: built in, or added by the person."""

    __tablename__ = "mail_senders"
    __table_args__ = (
        UniqueConstraint("address"),
        CheckConstraint("char_length(address) BETWEEN 3 AND 320", name="address_length"),
        CheckConstraint("address = lower(address)", name="address_lower"),
        CheckConstraint(_in("site", SITES), name="site_values"),
        CheckConstraint(_in("purpose", PURPOSES), name="purpose_values"),
    )

    address: Mapped[str] = mapped_column(Text)
    site: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    built_in: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class MailCheckRow(IdTimestampMixin, Base):
    """One run of reading mail. The search run it belongs to carries the jobs and decisions."""

    __tablename__ = "mail_checks"
    __table_args__ = (
        UniqueConstraint("search_run_id"),
        CheckConstraint(_in("trigger", CHECK_TRIGGERS), name="trigger_values"),
        CheckConstraint("ended IS NULL OR " + _in("ended", CHECK_ENDINGS), name="ended_values"),
        CheckConstraint(
            "emails_listed >= 0 AND emails_skipped >= 0 AND emails_read >= 0"
            " AND emails_unreadable >= 0",
            name="counts_not_negative",
        ),
        # a finished check's numbers add up (FR-026); a stopped or failed one need not
        CheckConstraint(
            "ended IS DISTINCT FROM 'finished'"
            " OR emails_listed = emails_skipped + emails_read + emails_unreadable",
            name="finished_counts_add_up",
        ),
    )

    search_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.search_runs.id", ondelete="CASCADE")
    )
    trigger: Mapped[str] = mapped_column(Text)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    emails_listed: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    emails_skipped: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    emails_read: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    emails_unreadable: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    more_remaining: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    ended: Mapped[str | None] = mapped_column(Text)


class MailReadMessageRow(IdTimestampMixin, Base):
    """The record that one email was read. Never the email itself."""

    __tablename__ = "mail_read_messages"
    __table_args__ = (
        UniqueConstraint("provider_message_id"),
        CheckConstraint("char_length(provider_message_id) BETWEEN 1 AND 64", name="id_length"),
        CheckConstraint("char_length(sender) BETWEEN 3 AND 320", name="sender_length"),
        CheckConstraint(_in("purpose", PURPOSES), name="purpose_values"),
        CheckConstraint(_in("outcome", READ_OUTCOMES), name="outcome_values"),
        CheckConstraint("jobs_found BETWEEN 0 AND 60", name="jobs_found_range"),
        CheckConstraint("jsonb_typeof(injection_signals) = 'array'", name="signals_array"),
        CheckConstraint("outcome <> 'read' OR reader IS NOT NULL", name="read_has_reader"),
        CheckConstraint("outcome = 'read' OR jobs_found = 0", name="jobs_only_when_read"),
        Index(
            "ix_mail_read_messages_mail_check_id",
            "mail_check_id",
            postgresql_where=text("mail_check_id IS NOT NULL"),
        ),
    )

    provider_message_id: Mapped[str] = mapped_column(Text)
    sender: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purpose: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    reader: Mapped[str | None] = mapped_column(Text)
    jobs_found: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    injection_signals: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    mail_check_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.mail_checks.id", ondelete="SET NULL")
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
