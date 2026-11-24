"""Mail from a job site's own domain (2026-11-22, amends FR-009): the domain is asked for next to
the listed addresses, only emails in which a reader finds jobs are kept, and nothing else is."""

from __future__ import annotations

from sqlalchemy import select, text
from tests.workflow.mail.test_ai_fallback import with_ai
from tests.workflow.mail.test_check import Env, count, the_check

from hiretitan.mail.application.ports import MessagePage
from hiretitan.mail.infra.models import MailReadMessageRow
from hiretitan.mail.infra.repos import SendersRepo
from hiretitan.mail_wiring import mail_run_details
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.search.infra.models import JobRow


async def messages(env: Env) -> list[MailReadMessageRow]:
    async with env.sessions() as session:
        return list((await session.scalars(select(MailReadMessageRow))).all())


async def test_the_query_asks_for_the_domains_of_the_sites_that_are_on(env: Env) -> None:
    env.add("linkedin-01")
    async with env.sessions() as session:
        await session.execute(
            text("UPDATE app.mail_senders SET enabled = false WHERE site = 'naukri'")
        )
        await session.commit()

    await env.check()

    (query,) = env.gmail.queries
    assert " OR linkedin.com" in query or "OR linkedin.com)" in query or "(linkedin.com" in query
    assert "indeed.com" in query
    assert "naukri.com" not in query  # naukri is switched off: its domain is not asked for either


async def test_an_alert_from_an_address_not_on_the_list_but_on_a_site_domain_is_read(
    env: Env,
) -> None:
    env.add("linkedin-01", as_sender="job-alerts@mail.linkedin.com")  # not a listed address

    run_id = await env.check()

    assert await count(env, JobRow) == 3
    (message,) = await messages(env)
    assert (message.outcome, message.reader, message.jobs_found) == ("read", "linkedin", 3)
    assert (await the_check(env, run_id)).emails_read == 1


async def test_mail_from_a_site_that_is_not_a_job_alert_is_dropped_quietly(env: Env) -> None:
    llm = FakeLlm()  # nothing scripted: the AI must not be asked about it
    with_ai(env, llm)
    env.add("unknown-01", as_sender="invitations@linkedin.com")  # a layout no reader knows

    run_id = await env.check()

    assert llm.calls == []
    (message,) = await messages(env)
    assert (message.outcome, message.reader, message.jobs_found) == ("no_jobs", "domain", 0)
    check = await the_check(env, run_id)
    assert (check.emails_listed, check.emails_unreadable) == (1, 0)  # not "could not read"
    assert await count(env, JobRow) == 0
    async with env.sessions() as session:
        mail = await mail_run_details(session, run_id)
    assert mail is not None
    assert mail.unreadable == []  # and not listed among the emails that could not be read


async def test_a_dropped_email_is_not_looked_at_again(env: Env) -> None:
    env.add("unknown-01", as_sender="invitations@linkedin.com")
    await env.check()
    env.gmail.fetched.clear()

    second = await env.check()

    assert env.gmail.fetched == []
    assert (await the_check(env, second)).emails_skipped == 1


async def test_a_look_alike_domain_is_never_read(env: Env) -> None:
    env.add("linkedin-01", as_sender="alerts@evillinkedin.com")
    env.gmail.pages = [MessagePage(["linkedin-01"], None)]  # Gmail lists it all the same

    run_id = await env.check()

    assert await count(env, JobRow) == 0
    (message,) = await messages(env)
    assert message.outcome == "unreadable"
    assert (await the_check(env, run_id)).emails_unreadable == 1


async def test_a_custom_sender_alone_asks_for_no_domain(env: Env) -> None:
    async with env.sessions() as session:
        await session.execute(text("UPDATE app.mail_senders SET enabled = false WHERE built_in"))
        await SendersRepo(session).add_custom("weekly@digest1.example.invalid")
        await session.commit()

    await env.check()

    (query,) = env.gmail.queries
    assert query.startswith("from:(weekly@digest1.example.invalid) after:")


async def test_a_listed_address_still_reads_as_before(env: Env) -> None:
    env.add("linkedin-01")  # jobalerts-noreply@linkedin.com is on the list

    await env.check()

    (message,) = await messages(env)
    assert (message.outcome, message.reader) == ("read", "linkedin")
