"""Mail checks: one active at a time, a ``failed`` ending, indexes for the alert look-ups.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "app"
OLD_ENDINGS = ("finished", "stopped", "access_ended", "gmail_unavailable")
NEW_ENDINGS = (*OLD_ENDINGS, "failed")


def _ended(values: tuple[str, ...]) -> str:
    return "ended IS NULL OR ended IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_mail_checks_ended_values", "mail_checks", schema=S, type_="check")
    op.create_check_constraint(
        "ck_mail_checks_ended_values", "mail_checks", _ended(NEW_ENDINGS), schema=S
    )
    # one mail check at a time, like one job search (a double click or a timer racing the button)
    op.create_index(
        "uq_workflow_runs_one_active_mail_check",
        "workflow_runs",
        ["workflow"],
        unique=True,
        schema=S,
        postgresql_where=sa.text(
            "workflow = 'mail_check' AND status IN ('queued', 'running', 'paused')"
        ),
    )
    # every alert posting looks up the jobs and the company of that name
    op.create_index(
        "ix_jobs_company_name_lower", "jobs", [sa.text("lower(company_name)")], schema=S
    )
    op.create_index(
        "ix_companies_name_lower",
        "companies",
        [sa.text("lower(name)")],
        schema=S,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_companies_name_lower", table_name="companies", schema=S)
    op.drop_index("ix_jobs_company_name_lower", table_name="jobs", schema=S)
    op.drop_index("uq_workflow_runs_one_active_mail_check", table_name="workflow_runs", schema=S)
    op.execute("UPDATE app.mail_checks SET ended = 'gmail_unavailable' WHERE ended = 'failed'")
    op.drop_constraint("ck_mail_checks_ended_values", "mail_checks", schema=S, type_="check")
    op.create_check_constraint(
        "ck_mail_checks_ended_values", "mail_checks", _ended(OLD_ENDINGS), schema=S
    )
