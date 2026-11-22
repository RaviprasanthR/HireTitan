"""Which senders a check reads (T036): US4 AS2 and AS3, through the whole check."""

from __future__ import annotations

from sqlalchemy import select, text
from tests.workflow.mail.test_check import Env, count, the_check

from hiretitan.mail.infra.models import MailReadMessageRow
from hiretitan.mail.infra.repos import SendersRepo
from hiretitan.search.infra.models import JobRow


async def test_US4_AS3_switched_off_site_not_queried(env: Env) -> None:
    env.add("linkedin-01", "naukri-01")
    async with env.sessions() as session:
        await session.execute(
            text("UPDATE app.mail_senders SET enabled = false WHERE site = 'linkedin'")
        )
        await session.commit()

    await env.check()

    (query,) = env.gmail.queries
    assert "linkedin.com" not in query
    assert "naukri.com" in query
    assert await count(env, JobRow) == 6  # naukri-01 only; the LinkedIn email is not even listed
    assert not any("linkedin" in (m.sender or "") for m in await _messages(env))


async def test_US4_AS2_no_jobs_from_added_sender_counted(env: Env) -> None:
    # an email from an address the person added, in a layout no reader knows, has no jobs to read
    env.add("unknown-01", as_sender="weekly@digest1.example.invalid")
    async with env.sessions() as session:
        await SendersRepo(session).add_custom("weekly@digest1.example.invalid")
        await session.commit()

    run_id = await env.check()

    check = await the_check(env, run_id)
    assert (check.emails_listed, check.emails_unreadable) == (1, 1)
    (query,) = env.gmail.queries
    assert "weekly@digest1.example.invalid" in query


async def _messages(env: Env) -> list[MailReadMessageRow]:
    async with env.sessions() as session:
        return list((await session.scalars(select(MailReadMessageRow))).all())
