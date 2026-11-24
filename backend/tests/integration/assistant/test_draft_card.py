"""002m quick actions: a draft ref shows in the chat as a card (FR-029, FR-009).

The person's own view: the written text and a link to the job's page. Never sent to the AI.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import make_env

from hiretitan.actions.cards import describe
from hiretitan.drafts.infra.repos import DraftsRepo


async def _start(sessions: async_sessionmaker[AsyncSession], kind: str):  # type: ignore[no-untyped-def]
    env = await make_env(sessions)
    async with sessions() as session:
        row = await DraftsRepo(session).start_writing(
            env.job_id,
            kind=kind,
            recipient_contact_id=None,
            recipient_name="Dana Osei",
            recipient_role=None,
            recipient_kind="recruiter",
            recipient_key="typed:dana osei",
        )
        await session.commit()
        return env, row.id


async def test_FR029_a_draft_being_written_has_no_text_yet(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    env, draft_id = await _start(sessions, "email")

    async with sessions() as session:
        card = await describe(session, f"draft:{draft_id}")

    assert card is not None
    assert card.kind == "draft"
    assert card.title == "Email"
    assert card.subtitle is not None
    assert "writing" in card.subtitle.casefold()
    assert card.lines == []
    assert card.link == f"/jobs/{env.job_id}"


async def test_FR029_a_ready_draft_shows_its_text(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, draft_id = await _start(sessions, "connection_request")
    async with sessions() as session:
        await DraftsRepo(session).save_result(
            draft_id,
            template="Hi {recipient_first_name}, glad to connect.",
            text="Hi Dana, glad to connect.",
            source="ai",
            cited_fact_ids=[],
            prompt_name=None,
            prompt_version=None,
            model=None,
        )
        await session.commit()

    async with sessions() as session:
        card = await describe(session, f"draft:{draft_id}")

    assert card is not None
    assert card.title == "LinkedIn connection message"
    assert card.subtitle is not None
    assert "Dana" in card.subtitle
    assert card.lines == ["Hi Dana, glad to connect."]


async def test_FR029_a_missing_draft_has_no_card(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        assert await describe(session, f"draft:{uuid4()}") is None
