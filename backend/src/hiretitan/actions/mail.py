"""Mikasa's actions on job-alert mail (002m contracts/actions.md, "Searches and mail").

The model never sees an email's text or the person's address: only whether Gmail is
connected, when it was last read, and which alert sites are on (FR-020, EC-12).
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select

from hiretitan.actions.spec import ActionContext, ActionSpec, ReadResult
from hiretitan.actions.text import bounded
from hiretitan.mail.infra.models import MailConnectionRow, MailSenderRow

GMAIL_PAGE = "/settings/gmail"


class NoArgs(BaseModel):
    pass


async def get_mail_status(ctx: ActionContext, args: NoArgs) -> ReadResult:
    connection = await ctx.session.scalar(select(MailConnectionRow).limit(1))
    senders = await ctx.session.scalars(
        select(MailSenderRow).order_by(MailSenderRow.built_in.desc(), MailSenderRow.site)
    )
    state = (
        "not_connected"
        if connection is None
        else "connected"
        if connection.state == "connected"
        else "needs_reconnect"
    )
    return ReadResult(
        items=[
            {
                "state": state,
                "connected": state == "connected",
                "page": GMAIL_PAGE,
                "last_check_started_at": (
                    connection.last_check_started_at.isoformat()
                    if connection is not None and connection.last_check_started_at
                    else None
                ),
                "last_error": bounded(connection.last_error).text or None if connection else None,
                "senders": [
                    {"site": bounded(s.site, 60).text, "built_in": s.built_in, "enabled": s.enabled}
                    for s in senders
                ],
            }
        ],
        total=1,
    )


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="get_mail_status",
        description="Whether Gmail is connected for job-alert mail, when it was last read, and "
        "which alert sites are on. Gmail itself is connected by the person in Settings.",
        args=NoArgs,
        kind="read",
        handler=get_mail_status,
        mirrors=("GET /mail/connection", "GET /mail/senders"),
    ),
)
