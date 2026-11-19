"""Mail connection, senders, read emails, mail checks and alert sightings (feature 002c).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
SITES = ("linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort", "other")
OLD_RUN_MODES = ("rules_and_ai", "rules_only")
NEW_RUN_MODES = (*OLD_RUN_MODES, "mail_alerts")
OLD_SOURCE_KINDS = ("company_board", "careers_page", "paste")
NEW_SOURCE_KINDS = (*OLD_SOURCE_KINDS, "email_alert")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _id_and_times() -> list[sa.Column]:  # type: ignore[type-arg]
    now = sa.func.now()
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    ]


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{S}.{target}.id"],
        name=f"fk_{table}_{column}_{target}",
        ondelete=ondelete,
    )


def _widen(table: str, constraint: str, column: str, values: tuple[str, ...]) -> None:
    op.drop_constraint(f"ck_{table}_{constraint}", table, schema=S, type_="check")
    op.create_check_constraint(f"ck_{table}_{constraint}", table, _in(column, values), schema=S)


def upgrade() -> None:
    op.create_table(
        "mail_connection",
        *_id_and_times(),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_check_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_mail_connection"),
        sa.UniqueConstraint("provider", name="uq_mail_connection_provider"),
        sa.CheckConstraint(_in("provider", ("gmail",)), name="ck_mail_connection_provider_values"),
        sa.CheckConstraint(
            _in("state", ("connected", "needs_reconnect")), name="ck_mail_connection_state_values"
        ),
        sa.CheckConstraint(
            "char_length(address) BETWEEN 3 AND 320", name="ck_mail_connection_address_length"
        ),
        sa.CheckConstraint(
            "char_length(last_error) <= 300", name="ck_mail_connection_last_error_length"
        ),
        schema=S,
    )

    op.create_table(
        "mail_senders",
        *_id_and_times(),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("built_in", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mail_senders"),
        sa.UniqueConstraint("address", name="uq_mail_senders_address"),
        sa.CheckConstraint(
            "char_length(address) BETWEEN 3 AND 320", name="ck_mail_senders_address_length"
        ),
        sa.CheckConstraint("address = lower(address)", name="ck_mail_senders_address_lower"),
        sa.CheckConstraint(_in("site", SITES), name="ck_mail_senders_site_values"),
        sa.CheckConstraint(_in("purpose", ("job_alert",)), name="ck_mail_senders_purpose_values"),
        schema=S,
    )

    op.create_table(
        "mail_checks",
        *_id_and_times(),
        sa.Column("search_run_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("emails_listed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("emails_skipped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("emails_read", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("emails_unreadable", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("more_remaining", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ended", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_mail_checks"),
        _fk("mail_checks", "search_run_id", "search_runs", "CASCADE"),
        sa.UniqueConstraint("search_run_id", name="uq_mail_checks_search_run_id"),
        sa.CheckConstraint(
            _in("trigger", ("daily", "button", "search_now")), name="ck_mail_checks_trigger_values"
        ),
        sa.CheckConstraint(
            "ended IS NULL OR "
            + _in("ended", ("finished", "stopped", "access_ended", "gmail_unavailable")),
            name="ck_mail_checks_ended_values",
        ),
        sa.CheckConstraint(
            "emails_listed >= 0 AND emails_skipped >= 0 AND emails_read >= 0"
            " AND emails_unreadable >= 0",
            name="ck_mail_checks_counts_not_negative",
        ),
        sa.CheckConstraint(
            "ended IS DISTINCT FROM 'finished'"
            " OR emails_listed = emails_skipped + emails_read + emails_unreadable",
            name="ck_mail_checks_finished_counts_add_up",
        ),
        schema=S,
    )

    op.create_table(
        "mail_read_messages",
        *_id_and_times(),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reader", sa.Text()),
        sa.Column("jobs_found", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "injection_signals",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("mail_check_id", sa.Uuid()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mail_read_messages"),
        _fk("mail_read_messages", "mail_check_id", "mail_checks", "SET NULL"),
        sa.UniqueConstraint(
            "provider_message_id", name="uq_mail_read_messages_provider_message_id"
        ),
        sa.CheckConstraint(
            "char_length(provider_message_id) BETWEEN 1 AND 64",
            name="ck_mail_read_messages_id_length",
        ),
        sa.CheckConstraint(
            "char_length(sender) BETWEEN 3 AND 320", name="ck_mail_read_messages_sender_length"
        ),
        sa.CheckConstraint(
            _in("purpose", ("job_alert",)), name="ck_mail_read_messages_purpose_values"
        ),
        sa.CheckConstraint(
            _in("outcome", ("read", "no_jobs", "unreadable", "needs_ai")),
            name="ck_mail_read_messages_outcome_values",
        ),
        sa.CheckConstraint(
            "jobs_found BETWEEN 0 AND 60", name="ck_mail_read_messages_jobs_found_range"
        ),
        sa.CheckConstraint(
            "outcome <> 'read' OR reader IS NOT NULL", name="ck_mail_read_messages_read_has_reader"
        ),
        sa.CheckConstraint(
            "outcome = 'read' OR jobs_found = 0", name="ck_mail_read_messages_jobs_only_when_read"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(injection_signals) = 'array'", name="ck_mail_read_messages_signals_array"
        ),
        schema=S,
    )
    op.create_index(
        "ix_mail_read_messages_mail_check_id",
        "mail_read_messages",
        ["mail_check_id"],
        schema=S,
        postgresql_where=sa.text("mail_check_id IS NOT NULL"),
    )

    op.create_table(
        "alert_sightings",
        *_id_and_times(),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("read_message_id", sa.Uuid()),
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("alert_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_alert_sightings"),
        _fk("alert_sightings", "job_id", "jobs", "CASCADE"),
        _fk("alert_sightings", "read_message_id", "mail_read_messages", "SET NULL"),
        # NULLs stay distinct on purpose: Disconnect sets read_message_id to NULL on every
        # sighting, and one job seen in two alerts must not then collide with itself
        sa.UniqueConstraint(
            "job_id", "read_message_id", name="uq_alert_sightings_job_id_read_message_id"
        ),
        sa.CheckConstraint(_in("site", SITES), name="ck_alert_sightings_site_values"),
        sa.CheckConstraint("char_length(link) <= 2000", name="ck_alert_sightings_link_length"),
        schema=S,
    )
    # no index on job_id alone: the unique above leads with it
    op.create_index(
        "ix_alert_sightings_read_message_id",
        "alert_sightings",
        ["read_message_id"],
        schema=S,
        postgresql_where=sa.text("read_message_id IS NOT NULL"),
    )

    _widen("search_runs", "mode_values", "mode", NEW_RUN_MODES)
    _widen("job_sources", "kind_values", "kind", NEW_SOURCE_KINDS)


def downgrade() -> None:
    # Rows holding the new values would block the old checks, so they are converted, not deleted:
    # a mail run becomes a rules-only run (its check and read-email records go with the tables
    # below), an email source becomes a paste source (skipped where the job already has that
    # address as a paste). Nothing the person can see as a job is lost.
    op.execute(
        "DELETE FROM app.job_sources s WHERE s.kind = 'email_alert' AND EXISTS ("
        " SELECT 1 FROM app.job_sources p"
        " WHERE p.job_id = s.job_id AND p.url = s.url AND p.kind = 'paste')"
    )
    op.execute("UPDATE app.job_sources SET kind = 'paste' WHERE kind = 'email_alert'")
    op.execute("UPDATE app.search_runs SET mode = 'rules_only' WHERE mode = 'mail_alerts'")
    _widen("job_sources", "kind_values", "kind", OLD_SOURCE_KINDS)
    _widen("search_runs", "mode_values", "mode", OLD_RUN_MODES)

    op.drop_table("alert_sightings", schema=S)
    op.drop_table("mail_read_messages", schema=S)
    op.drop_table("mail_checks", schema=S)
    op.drop_table("mail_senders", schema=S)
    op.drop_table("mail_connection", schema=S)
