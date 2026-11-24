"""002m T014: the stored contents of contacts, notes, interview details and resume files never
reach the AI through Mikasa (FR-022, FR-022a, SC-010, research R5).

Distinctive synthetic values are planted in every private field. Scripted turns call every
private read action through the real catalogue; every request the fake LLM received is then
searched for each value.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.registry import build_catalogue
from hiretitan.assistant.application.turn import DoneEvent, TurnDeps, begin, run_turn
from hiretitan.assistant.infra.repos import ConversationsRepo
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.assistant_wiring import CatalogAdapter
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import TextDelta, ToolCall
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.profile.infra.repos import ResumeFilesRepo
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, JobsRepo, NotesRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"
PLANTED = (
    "Zebulon Quarrington",
    "zebulon.private@example.invalid",
    "+1 555 0177",
    "https://example.invalid/in/zebulon-private",
    "note-distinctive-4410",
    "pipeline-contact Philippa Vossberg",
    "firm-distinctive-Hirequest",
    "interviewer-distinctive Ottoline Brack",
    "feedback-distinctive-9921",
    "question-distinctive-3108",
    "answer-distinctive-5546",
    "resume-file-distinctive-7781.pdf",
)


class NoClaims:
    async def unbacked(self, text: str, context: str) -> list[str]:
        return []


async def plant(sessions: async_sessionmaker[AsyncSession]) -> dict[str, UUID]:
    async with sessions() as session:
        acme = await CompaniesRepo(session).add(name="Acme", origin="user", resolution="verified")
        await ContactsRepo(session).add(
            acme.id,
            ContactFields(
                name="Zebulon Quarrington",
                role="Talent Partner",
                email="zebulon.private@example.invalid",
                phone="+1 555 0177",
                linkedin_url="https://example.invalid/in/zebulon-private",
            ),
            source="typed",
        )
        await NotesRepo(session).set(acme.id, "Met them note-distinctive-4410", source="typed")
        job = await JobsRepo(session).add(
            company_id=acme.id,
            company_name="Acme",
            title="Backend Engineer",
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="",
            state="applied",
            applied_on=date(2026, 11, 20),
        )
        repo = InterviewsRepo(session)
        await repo.upsert_contact(job.id, ContactFields(name="pipeline-contact Philippa Vossberg"))
        await repo.set_source(job.id, "hiring_firm", "firm-distinctive-Hirequest")
        first = await repo.add_round(
            job.id,
            kind="technical",
            scheduled_at=NOW + timedelta(days=1),
            interviewers="interviewer-distinctive Ottoline Brack",
        )
        await repo.update_round(first.id, {"feedback": "feedback-distinctive-9921"})
        await repo.add_question(first.id, "question-distinctive-3108", "answer-distinctive-5546")
        await ResumeFilesRepo(session).create(
            kind="upload_pdf",
            original_name="resume-file-distinctive-7781.pdf",
            size_bytes=10,
            sha256="c" * 64,
        )
        conversation = await ConversationsRepo(session).create(now=NOW)
        await session.commit()
        return {"company": acme.id, "job": job.id, "conversation": conversation.id}


def deps(sessions: async_sessionmaker[AsyncSession], llm: FakeLlm) -> TurnDeps:
    return TurnDeps(
        llm=llm,
        catalog=CatalogAdapter(build_catalogue(), sessions),
        store=SqlTurnStore(sessions),
        claims=NoClaims(),
        prompt=PromptRegistry(PROMPTS).load("mikasa_chat"),
        now=lambda: NOW,
    )


def everything_sent(llm: FakeLlm) -> str:
    return json.dumps(
        [
            [m.text or "", m.arguments_json or "", m.tool_name or ""]
            for call in llm.converse_calls
            for m in call.messages
        ]
    )


async def run(d: TurnDeps, conversation: UUID, text: str) -> list[Any]:
    await begin(d, conversation, text)
    return [event async for event in run_turn(d, conversation, page="/")]


async def test_SC010_no_private_value_in_any_llm_request(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    ids = await plant(sessions)
    company, job = f"company:{ids['company']}", f"job:{ids['job']}"
    llm = FakeLlm()
    llm.add_turn(
        ToolCall("a", "list_contacts", json.dumps({"company": company})),
        ToolCall("b", "find_contact", json.dumps({"name": "zebulon"})),
        ToolCall("c", "get_company_note", json.dumps({"company": company})),
        ToolCall("d", "get_interview", json.dumps({"job": job})),
        ToolCall("e", "list_rounds", "{}"),
        ToolCall("f", "list_resume_files", "{}"),
        ToolCall("g", "search_companies", "{}"),
        ToolCall("h", "get_pipeline_summary", "{}"),
    )
    llm.add_turn(TextDelta("Here they are."))
    d = deps(sessions, llm)

    events = await run(d, ids["conversation"], "Who do I know at Acme and when is my interview?")

    assert isinstance(events[-1], DoneEvent)
    sent = everything_sent(llm)
    assert "contact:" in sent  # the refs did go out
    assert "round:" in sent
    for value in PLANTED:
        assert value not in sent, value


async def test_FR022a_summary_of_private_content_declined(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    ids = await plant(sessions)
    llm = FakeLlm()
    llm.add_turn(ToolCall("a", "get_interview", json.dumps({"job": f"job:{ids['job']}"})))
    llm.add_turn(
        TextDelta(
            "Your interview notes stay out of the AI, so I can't summarise them. You can read "
            f"them on [[page:/jobs/{ids['job']}]]."
        )
    )

    events = await run(deps(sessions, llm), ids["conversation"], "Summarise my Zoho interview")

    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert f"[[page:/jobs/{ids['job']}]]" in done.text  # the link survives the reply check
    sent = everything_sent(llm)
    for value in PLANTED:
        assert value not in sent, value
