"""Mikasa's conversations, messages, confirm cards and change records (002m data-model.md).

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
AUTHORS = ("person", "mikasa")
MESSAGE_STATUSES = ("complete", "stopped", "failed")
CARD_STATES = ("proposed", "applying", "applied", "cancelled", "expired", "failed")
EMPTY_LIST = sa.text("'[]'::jsonb")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _created_at() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{S}.{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("turn_running", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("turn_started_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_conversations"),
        sa.CheckConstraint(
            "char_length(title) <= 80", name="ck_assistant_conversations_title_length"
        ),
        schema=S,
    )
    op.create_index(
        "ix_assistant_conversations_last_used_at",
        "assistant_conversations",
        [sa.text("last_used_at DESC")],
        schema=S,
    )

    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("refs", postgresql.JSONB(), server_default=EMPTY_LIST, nullable=False),
        sa.Column("tool_trace", postgresql.JSONB(), server_default=EMPTY_LIST, nullable=False),
        sa.Column("signals", postgresql.JSONB(), server_default=EMPTY_LIST, nullable=False),
        sa.Column("error", postgresql.JSONB()),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_messages"),
        _fk("assistant_messages", "conversation_id", "assistant_conversations"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_assistant_messages_seq"),
        sa.CheckConstraint(_in("author", AUTHORS), name="ck_assistant_messages_author_values"),
        sa.CheckConstraint(
            _in("status", MESSAGE_STATUSES), name="ck_assistant_messages_status_values"
        ),
        sa.CheckConstraint("seq >= 1", name="ck_assistant_messages_seq_positive"),
        sa.CheckConstraint(
            "char_length(text) <= CASE WHEN author = 'person' THEN 2000 ELSE 4000 END",
            name="ck_assistant_messages_text_length",
        ),
        schema=S,
    )

    op.create_table(
        "assistant_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.Column("fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_cards"),
        _fk("assistant_cards", "conversation_id", "assistant_conversations"),
        _fk("assistant_cards", "message_id", "assistant_messages"),
        sa.CheckConstraint(_in("state", CARD_STATES), name="ck_assistant_cards_state_values"),
        sa.CheckConstraint(
            "jsonb_typeof(items) = 'array' AND jsonb_array_length(items) BETWEEN 1 AND 25",
            name="ck_assistant_cards_items_count",
        ),
        sa.CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 2000", name="ck_assistant_cards_summary_length"
        ),
        schema=S,
    )
    op.create_index(
        "ix_assistant_cards_conversation_id", "assistant_cards", ["conversation_id"], schema=S
    )
    op.create_index("ix_assistant_cards_message_id", "assistant_cards", ["message_id"], schema=S)

    op.create_table(
        "assistant_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid()),
        sa.Column("card_id", sa.Uuid()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=False),
        sa.Column("after", postgresql.JSONB(), nullable=False),
        sa.Column("created_rows", postgresql.JSONB(), server_default=EMPTY_LIST, nullable=False),
        sa.Column("undoable_until", sa.DateTime(timezone=True)),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_changes"),
        _fk("assistant_changes", "conversation_id", "assistant_conversations"),
        _fk("assistant_changes", "message_id", "assistant_messages"),
        _fk("assistant_changes", "card_id", "assistant_cards"),
        sa.CheckConstraint(
            "(message_id IS NULL) <> (card_id IS NULL)", name="ck_assistant_changes_one_source"
        ),
        schema=S,
    )
    op.create_index(
        "ix_assistant_changes_target",
        "assistant_changes",
        ["target_kind", "target_id", sa.text("created_at DESC")],
        schema=S,
    )
    for column in ("conversation_id", "message_id", "card_id"):
        op.create_index(f"ix_assistant_changes_{column}", "assistant_changes", [column], schema=S)


def downgrade() -> None:
    op.drop_table("assistant_changes", schema=S)
    op.drop_table("assistant_cards", schema=S)
    op.drop_table("assistant_messages", schema=S)
    op.drop_table("assistant_conversations", schema=S)
