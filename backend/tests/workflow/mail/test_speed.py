"""Fifty emails in good time (T039): SC-005. A generous bound so CI machines pass."""

from __future__ import annotations

import time

from sqlalchemy import func, select
from tests.workflow.mail.test_check import Env, the_check

from hiretitan.search.infra.models import JobRow

BOUND_SECONDS = 120.0


async def test_SC005_fifty_emails_under_two_minutes(env: Env) -> None:
    # ``copies`` names its files copy000...; the first site's set is renamed so both sets stay
    for n, name in enumerate(env.copies("linkedin-01", 25)):
        path = env.mailbox / "messages" / f"{name}.eml"
        path.rename(env.mailbox / "messages" / f"linkedin{n:03d}.eml")
    env.copies("naukri-01", 25)
    started = time.monotonic()

    run_id = await env.check()

    elapsed = time.monotonic() - started
    check = await the_check(env, run_id)
    assert (check.emails_listed, check.emails_read, check.ended) == (50, 50, "finished")
    assert elapsed < BOUND_SECONDS
    async with env.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(JobRow)) == 9  # one each
