"""ORM models for Mikasa's tables (002m data-model.md, migration 0026).

The database repeats every rule as a named constraint, so a repository bug cannot store a value
the model forbids. Delete all truncates every ``app`` table, so these need no extra code there.
"""

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import APP_SCHEMA, Base
from hiretitan.platform.db.ids import uuid7

AUTHORS = ("person", "mikasa")
MESSAGE_STATUSES = ("complete", "stopped", "failed")
CARD_STATES = ("proposed", "applying", "applied", "cancelled", "expired", "failed")
PERSON_TEXT_MAX = 2000
MIKASA_TEXT_MAX = 4000
TITLE_MAX = 80
CARD_ITEMS_MAX = 25

_EMPTY_LIST = text("'[]'::jsonb")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConversationRow(Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (
        CheckConstraint(f"char_length(title) <= {TITLE_MAX}", name="title_length"),
        Index("ix_assistant_conversations_last_used_at", text("last_used_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    title: Mapped[str | None] = mapped_column(Text)
    turn_running: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # A turn running for more than 120 s is treated as ended (a crash or a lost connection).
    turn_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StagedRow(Base):
    """A pasted job post a conversation is holding until the person says yes or no (002m).

    ``job_id`` is a job in the hidden ``staged`` state; it is empty while the person has only
    chosen what they want and not pasted yet. ``kind`` is empty while they have pasted first.
    """

    __tablename__ = "assistant_staged"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('connection_request', 'referral_message', 'email')", name="kind_values"
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.assistant_conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    kind: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.jobs.id", ondelete="SET NULL")
    )
    # the post did not say its title or company: the person is asked for them
    needs_details: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = _created_at()


class MessageRow(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_assistant_messages_seq"),
        CheckConstraint(_in("author", AUTHORS), name="author_values"),
        CheckConstraint(_in("status", MESSAGE_STATUSES), name="status_values"),
        CheckConstraint("seq >= 1", name="seq_positive"),
        CheckConstraint(
            f"char_length(text) <= CASE WHEN author = 'person' THEN {PERSON_TEXT_MAX} "
            f"ELSE {MIKASA_TEXT_MAX} END",
            name="text_length",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.assistant_conversations.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    author: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    refs: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=_EMPTY_LIST)
    tool_trace: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=_EMPTY_LIST)
    signals: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=_EMPTY_LIST)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()


class CardRow(Base):
    """A confirm card for one or more risky changes (research R7)."""

    __tablename__ = "assistant_cards"
    __table_args__ = (
        CheckConstraint(_in("state", CARD_STATES), name="state_values"),
        CheckConstraint(
            f"jsonb_typeof(items) = 'array' AND jsonb_array_length(items) BETWEEN 1 AND "
            f"{CARD_ITEMS_MAX}",
            name="items_count",
        ),
        CheckConstraint("char_length(summary) BETWEEN 1 AND 2000", name="summary_length"),
        Index("ix_assistant_cards_conversation_id", "conversation_id"),
        Index("ix_assistant_cards_message_id", "message_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.assistant_conversations.id", ondelete="CASCADE")
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.assistant_messages.id", ondelete="CASCADE")
    )
    state: Mapped[str] = mapped_column(Text)
    items: Mapped[list[Any]] = mapped_column(JSONB)
    fingerprints: Mapped[dict[str, Any]] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text)
    result: Mapped[list[Any] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class ChangeRow(Base):
    """A change Mikasa applied, at once (small) or from a card (research R6)."""

    __tablename__ = "assistant_changes"
    __table_args__ = (
        CheckConstraint("(message_id IS NULL) <> (card_id IS NULL)", name="one_source"),
        CheckConstraint("char_length(summary) <= 2000", name="summary_length"),
        Index(
            "ix_assistant_changes_target",
            "target_kind",
            "target_id",
            text("created_at DESC"),
        ),
        Index("ix_assistant_changes_conversation_id", "conversation_id"),
        Index("ix_assistant_changes_message_id", "message_id"),
        Index("ix_assistant_changes_card_id", "card_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.assistant_conversations.id", ondelete="CASCADE")
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.assistant_messages.id", ondelete="CASCADE")
    )
    card_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.assistant_cards.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)  # what it did, for the chat history
    target_kind: Mapped[str] = mapped_column(Text)
    target_id: Mapped[UUID] = mapped_column()
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_rows: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=_EMPTY_LIST)
    undoable_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
