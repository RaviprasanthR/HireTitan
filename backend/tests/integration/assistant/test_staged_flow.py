"""002m quick flow: choose a draft, paste a post, get the draft, then say yes or no to saving.

Nothing is saved before the yes (Ravi, 2026-11-24): a pasted post is held as a hidden ``staged``
job that no list shows; yes makes it an Explore job, no deletes it and its draft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import DraftsEnv, make_env

from hiretitan import prompts as hiretitan_prompts
from hiretitan.assistant.application.ports import DraftRefusedError, StagedRefusedError
from hiretitan.assistant.infra.models import MessageRow
from hiretitan.drafts.infra.models import OutreachDraftRow
from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.search.infra.models import JobRow
from hiretitan.staged_wiring import StagedFlowImpl

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
POST = (
    "Senior Platform Engineer at Initech\n\nWe build the platform that runs payment services for "
    "a large retailer. You will own services end to end, in Python and PostgreSQL, with a small "
    "friendly team. Apply at https://jobs.example.com/initech/platform-1"
)
IDENTITY = {"title": "Senior Platform Engineer", "company": "Initech"}


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Flow:
    flow: StagedFlowImpl
    env: DraftsEnv
    queue: Queue
    conversation: UUID
    sessions: async_sessionmaker[AsyncSession]
    published: list[list[list[str]]]

    async def jobs(self, state: str) -> list[JobRow]:
        async with self.sessions() as session:
            rows = await session.scalars(select(JobRow).where(JobRow.state == state))
            return list(rows)

    async def texts(self) -> list[str]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(MessageRow.text).where(MessageRow.conversation_id == self.conversation)
            )
            return list(rows)


@pytest.fixture
async def flow(sessions: async_sessionmaker[AsyncSession]) -> Flow:
    from hiretitan.assistant.infra.repos import ConversationsRepo

    env = await make_env(sessions)
    async with sessions() as session:
        conversation = (await ConversationsRepo(session).create(now=NOW)).id
        await session.commit()
    queue = Queue()
    published: list[list[list[str]]] = []

    async def publish(keys: list[list[str]]) -> None:
        published.append(keys)

    impl = StagedFlowImpl(
        sessions,
        env.llm,
        PromptRegistry(Path(hiretitan_prompts.__file__).parent),
        queue,
        "fake",
        lambda: NOW,
        publish,
    )
    return Flow(impl, env, queue, conversation, sessions, published)


async def test_begin_asks_for_the_post(flow: Flow) -> None:
    view = await flow.flow.begin(flow.conversation, "email")

    assert (view.step, view.kind, view.label) == ("need_post", "email", None)
    texts = await flow.texts()
    assert texts[0] == "Email"
    assert "Paste the job post" in texts[1]


async def test_post_after_choosing_writes_the_draft_and_saves_nothing(flow: Flow) -> None:
    flow.env.llm.add(IDENTITY, task="extract_posting_identity")
    await flow.flow.begin(flow.conversation, "referral_message")

    view = await flow.flow.hold_post(flow.conversation, POST)

    assert view.step == "drafting"
    assert view.label == "Senior Platform Engineer at Initech"
    assert view.draft_ref is not None
    assert len(flow.queue.enqueued) == 1
    # held, hidden: not in Explore or the pipeline
    staged = await flow.jobs("staged")
    assert [j.title for j in staged] == ["Senior Platform Engineer"]
    assert [j.company_name for j in staged] == ["Initech"]
    async with flow.sessions() as session:
        listed = await session.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.state == "explore")
        )
    assert listed == 1  # only the job make_env made; the post is not shown


async def test_post_first_then_choose(flow: Flow) -> None:
    flow.env.llm.add(IDENTITY, task="extract_posting_identity")

    after_post = await flow.flow.hold_post(flow.conversation, POST)
    assert (after_post.step, after_post.kind) == ("need_kind", None)
    assert flow.queue.enqueued == []

    after_choice = await flow.flow.choose(flow.conversation, "connection_request")

    assert after_choice.step == "drafting"
    assert len(flow.queue.enqueued) == 1


async def test_the_post_text_never_enters_the_chat_history(flow: Flow) -> None:
    flow.env.llm.add(IDENTITY, task="extract_posting_identity")

    await flow.flow.hold_post(flow.conversation, POST)

    for text in await flow.texts():
        assert "friendly team" not in text
        assert "PostgreSQL" not in text


async def test_the_post_reaches_the_ai_only_inside_a_data_block(flow: Flow) -> None:
    flow.env.llm.add(IDENTITY, task="extract_posting_identity")

    await flow.flow.hold_post(flow.conversation, POST)

    call = next(c for c in flow.env.llm.calls if c.task == "extract_posting_identity")
    assert "friendly team" not in call.prompt.system
    assert "friendly team" not in call.prompt.user
    assert any("friendly team" in block.text for block in call.untrusted_blocks)


async def test_a_post_the_ai_cannot_read_asks_for_title_and_company(flow: Flow) -> None:
    flow.env.llm.add(AiUnavailable("key_missing", "no key"), task="extract_posting_identity")

    view = await flow.flow.hold_post(flow.conversation, POST)

    assert view.step == "need_details"
    assert len(await flow.jobs("staged")) == 1


async def test_a_bare_link_asks_for_title_and_company(flow: Flow) -> None:
    view = await flow.flow.hold_post(
        flow.conversation, "https://jobs.example.com/initech/platform-9"
    )

    assert view.step == "need_details"
    assert not [c for c in flow.env.llm.calls if c.task == "extract_posting_identity"]  # no text


async def test_details_then_the_flow_goes_on(flow: Flow) -> None:
    await flow.flow.begin(flow.conversation, "email")
    await flow.flow.hold_post(flow.conversation, "https://jobs.example.com/initech/platform-9")

    view = await flow.flow.details(flow.conversation, "Platform Engineer", "Initech")

    assert view.step == "drafting"  # the kind was chosen first, so the draft starts
    assert view.label == "Platform Engineer at Initech"
    staged = await flow.jobs("staged")
    assert [(j.title, j.company_name) for j in staged] == [("Platform Engineer", "Initech")]


async def test_yes_makes_it_an_explore_job(flow: Flow) -> None:
    flow.env.llm.add(IDENTITY, task="extract_posting_identity")
    await flow.flow.begin(flow.conversation, "email")
    await flow.flow.hold_post(flow.conversation, POST)

    said = await flow.flow.save(flow.conversation)

    assert "Senior Platform Engineer at Initech" in said
    assert await flow.jobs("staged") == []
    titles = {j.title for j in await flow.jobs("explore")}
    assert "Senior Platform Engineer" in titles
    assert await flow.flow.view(flow.conversation) is None
    assert ["jobs"] in [key for keys in flow.published for key in keys]


async def test_no_deletes_the_job_and_its_draft(flow: Flow) -> None:
    flow.env.llm.add(IDENTITY, task="extract_posting_identity")
    await flow.flow.begin(flow.conversation, "email")
    await flow.flow.hold_post(flow.conversation, POST)

    await flow.flow.discard(flow.conversation)

    assert await flow.jobs("staged") == []
    assert "Senior Platform Engineer" not in {j.title for j in await flow.jobs("explore")}
    async with flow.sessions() as session:
        drafts = await session.scalar(
            select(func.count())
            .select_from(OutreachDraftRow)
            .where(OutreachDraftRow.recipient_name == "Hiring team")
        )
    assert drafts == 0
    assert await flow.flow.view(flow.conversation) is None


async def test_a_job_the_person_already_has_is_not_staged_or_asked_about(flow: Flow) -> None:
    flow.env.llm.add(IDENTITY, IDENTITY, task="extract_posting_identity")
    await flow.flow.hold_post(flow.conversation, POST)
    await flow.flow.save(flow.conversation)

    again = await flow.flow.hold_post(flow.conversation, POST)

    assert again.already_saved is True
    assert await flow.jobs("staged") == []


async def test_pasting_again_replaces_the_held_post(flow: Flow) -> None:
    flow.env.llm.add(
        IDENTITY, {"title": "Data Engineer", "company": "Globex"}, task="extract_posting_identity"
    )
    await flow.flow.hold_post(flow.conversation, POST)

    await flow.flow.hold_post(
        flow.conversation,
        POST.replace("Initech", "Globex").replace("platform-1", "data-2"),
    )

    staged = await flow.jobs("staged")
    assert [j.company_name for j in staged] == ["Globex"]


async def test_choosing_with_no_post_is_refused(flow: Flow) -> None:
    with pytest.raises(StagedRefusedError):
        await flow.flow.choose(flow.conversation, "email")


async def test_a_draft_that_cannot_start_says_why_and_keeps_the_post(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from hiretitan.assistant.infra.repos import ConversationsRepo

    env = await make_env(sessions, with_profile=False)
    async with sessions() as session:
        conversation = (await ConversationsRepo(session).create(now=NOW)).id
        await session.commit()

    async def publish(keys: list[list[str]]) -> None:
        return None

    impl = StagedFlowImpl(
        sessions,
        env.llm,
        PromptRegistry(Path(hiretitan_prompts.__file__).parent),
        Queue(),
        "fake",
        lambda: NOW,
        publish,
    )
    env.llm.add(IDENTITY, task="extract_posting_identity")
    await impl.hold_post(conversation, POST)

    with pytest.raises(DraftRefusedError, match="Finish your profile first"):
        await impl.choose(conversation, "email")

    view = await impl.view(conversation)
    assert view is not None
    assert view.step == "need_kind"  # the post is still held
