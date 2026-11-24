"""002m T011: Mikasa's reads of private data: contacts, notes, interview details and resume files
(contracts/actions.md; FR-022, EC-14, research R5).

Each returns refs and labels only. Distinctive synthetic values are planted in every private
field, and none may appear in what the model would see.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionContext, PrivateResult, model_facing
from hiretitan.profile.infra.repos import ResumeFilesRepo
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, JobsRepo, NotesRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PLANTED = (
    "Quillon Fairweather",
    "quillon.private@example.invalid",
    "+1 555 0199",
    "distinctive-note-7731",
    "Interviewer Ottoline Brack",
    "feedback-distinctive-2290",
    "question-distinctive-8812",
    "answer-distinctive-6604",
    "resume-file-distinctive-3317.pdf",
)


async def run(session: AsyncSession, action: str, **args: Any) -> Any:
    spec = build_catalogue().get(action)
    assert spec is not None, action
    assert spec.kind == "read"
    assert spec.private is True
    return await spec.handler(ActionContext(session, NOW), spec.args(**args))


def assert_private(result: Any) -> None:
    assert isinstance(result, PrivateResult)
    text = json.dumps(model_facing(result), default=str)
    for value in PLANTED:
        assert value not in text, value
    for item in model_facing(result)["items"]:
        assert set(item) == {"ref", "label"}


async def world(session: AsyncSession) -> dict[str, UUID]:
    acme = await CompaniesRepo(session).add(name="Acme", origin="user", resolution="verified")
    contact = await ContactsRepo(session).add(
        acme.id,
        ContactFields(
            name="Quillon Fairweather",
            role="Talent Partner",
            email="quillon.private@example.invalid",
            phone="+1 555 0199",
        ),
        source="typed",
    )
    await ContactsRepo(session).add(acme.id, ContactFields(name="Ann Other"), source="typed")
    await NotesRepo(session).set(acme.id, "Met at a meetup distinctive-note-7731", source="typed")
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
    first = await repo.add_round(
        job.id,
        kind="technical",
        scheduled_at=NOW + timedelta(days=2),
        interviewers="Interviewer Ottoline Brack",
    )
    await repo.update_round(first.id, {"feedback": "feedback-distinctive-2290"})
    await repo.add_question(first.id, "question-distinctive-8812", "answer-distinctive-6604")
    await repo.upsert_contact(job.id, ContactFields(name="Quillon Fairweather"))
    return {"company": acme.id, "contact": contact.id, "job": job.id, "round": first.id}


async def test_FR022_list_contacts_returns_refs_and_labels(db_session: AsyncSession) -> None:
    ids = await world(db_session)

    result = await run(db_session, "list_contacts", company=f"company:{ids['company']}")

    assert_private(result)
    assert result.total == 2
    assert f"contact:{ids['contact']}" in [item.ref for item in result.items]
    assert result.items[0].label.startswith("a contact at Acme")


async def test_EC14_find_contact_returns_ref(db_session: AsyncSession) -> None:
    ids = await world(db_session)

    result = await run(db_session, "find_contact", name="quillon")
    none = await run(db_session, "find_contact", name="nobody-by-that-name")

    assert_private(result)
    assert [item.ref for item in result.items] == [f"contact:{ids['contact']}"]
    assert none.items == []


async def test_FR022_company_note_is_a_ref(db_session: AsyncSession) -> None:
    ids = await world(db_session)

    result = await run(db_session, "get_company_note", company=f"company:{ids['company']}")

    assert_private(result)
    assert [item.ref for item in result.items] == [f"note:{ids['company']}"]
    assert result.items[0].label == "your note on Acme"


async def test_FR022_interview_details_are_refs(db_session: AsyncSession) -> None:
    ids = await world(db_session)

    result = await run(db_session, "get_interview", job=f"job:{ids['job']}")
    upcoming = await run(db_session, "list_rounds")

    assert_private(result)
    assert_private(upcoming)
    refs = [item.ref for item in result.items]
    assert f"interview:{ids['job']}" in refs
    assert f"round:{ids['round']}" in refs
    assert any(ref.startswith("question:") for ref in refs)
    assert [item.ref for item in upcoming.items] == [f"round:{ids['round']}"]
    assert upcoming.items[0].label.startswith("an interview round for Backend Engineer at Acme")


async def test_FR022_resume_files_are_refs(db_session: AsyncSession) -> None:
    await ResumeFilesRepo(db_session).create(
        kind="upload_pdf",
        original_name="resume-file-distinctive-3317.pdf",
        size_bytes=10,
        sha256="b" * 64,
    )

    result = await run(db_session, "list_resume_files")

    assert_private(result)
    assert result.total == 1
    assert result.items[0].ref.startswith("resume_file:")
