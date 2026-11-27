"""002m quick actions: the chat's drafts go through the drafts use case (FR-029, amended).

The same rules as the job page's Write button: a confirmed profile, a known job, the AI key; no
name means the hiring team.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import make_env

from hiretitan.assistant.application.ports import DraftRefusedError
from hiretitan.drafts.infra.repos import DraftsRepo
from hiretitan.staged_wiring import draft_starter


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


async def test_FR029_email_to_the_hiring_team_is_started(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    env = await make_env(sessions)
    queue = Queue()
    start = draft_starter(sessions, queue, "fake")

    started = await start(env.job_id, "email", None, None)

    assert started.job_label == "Backend Engineer at Acme"
    async with sessions() as session:
        row = await DraftsRepo(session).get(started.draft_id)
    assert row is not None
    assert (row.kind, row.status) == ("email", "writing")
    assert row.recipient_name == "Hiring team"
    assert row.recipient_kind == "hiring_manager"
    assert len(queue.enqueued) == 1


async def test_FR029_a_named_recipient_and_writing_again(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    env = await make_env(sessions)
    start = draft_starter(sessions, Queue(), "fake")
    first = await start(env.job_id, "connection_request", "Dana Osei", "recruiter")
    async with sessions() as session:
        await DraftsRepo(session).save_result(
            first.draft_id,
            template="Hi {recipient_first_name}",
            text="Hi Dana",
            source="fallback",
            cited_fact_ids=[],
            prompt_name=None,
            prompt_version=None,
            model=None,
        )
        await session.commit()

    again = await start(env.job_id, "connection_request", "Dana Osei", "recruiter")

    async with sessions() as session:
        row = await DraftsRepo(session).get(again.draft_id)
    assert row is not None
    assert row.status == "writing"  # the quick action always writes afresh
    assert row.recipient_kind == "recruiter"


@pytest.mark.parametrize(
    ("with_profile", "message"),
    [(False, "Finish your profile first, then write a draft.")],
)
async def test_FR029_refusals_come_back_in_words(
    sessions: async_sessionmaker[AsyncSession], with_profile: bool, message: str
) -> None:
    env = await make_env(sessions, with_profile=with_profile)
    start = draft_starter(sessions, Queue(), "fake")

    with pytest.raises(DraftRefusedError) as refused:
        await start(env.job_id, "referral_message", None, None)

    assert refused.value.message == message


async def test_FR029_unknown_job_is_refused(sessions: async_sessionmaker[AsyncSession]) -> None:
    start = draft_starter(sessions, Queue(), "fake")

    with pytest.raises(DraftRefusedError, match="no longer in your list"):
        await start(uuid4(), "email", None, None)
