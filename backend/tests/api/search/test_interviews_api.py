"""Interview tracking endpoints (feature 002e, contracts/rest-api.md)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.interviews import SearchInterviewsApiDeps, create_interviews_router
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
TODAY = date(2026, 11, 6)


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchInterviewsApiDeps(sessions=sessions)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_interviews_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def add_job(env: Env, title: str = "Backend Engineer", *, state: str = "applied") -> UUID:
    async with env.sessions() as session:
        companies = CompaniesRepo(session)
        known = [c for c in await companies.list_all() if c.name == "Acme"]
        company = (
            known[0]
            if known
            else await companies.add(name="Acme", origin="user", resolution="verified")
        )
        job = await JobsRepo(session).add(
            company_id=company.id,
            company_name="Acme",
            title=title,
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="d",
            state=state,
            applied_on=TODAY if state == "applied" else None,
            inquired_on=TODAY if state == "inquired" else None,
        )
        await session.commit()
        return job.id


async def test_read_empty_details(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.get(f"/api/v1/jobs/{job_id}/interview")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": str(job_id),
        "can_edit": True,
        "can_add_round": True,
        "contact": None,
        "source": None,
        "rounds": [],
        "status": {"state": "applied", "round": None},
        # feature 002f: no resume is recorded for the job yet
        "resume": {"state": "none", "resume_file_id": None, "name": None, "added_on": None},
    }


async def test_read_unknown_job_404(env: Env) -> None:
    response = await env.client.get("/api/v1/jobs/00000000-0000-7000-8000-000000000999/interview")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("state", "editable"),
    [("applied", True), ("inquired", True), ("explore", False), ("skipped", False)],
)
async def test_can_edit_false_outside_the_pipeline(env: Env, state: str, editable: bool) -> None:
    job_id = await add_job(env, state=state)

    body = (await env.client.get(f"/api/v1/jobs/{job_id}/interview")).json()

    assert body["can_edit"] is editable
    assert body["can_add_round"] is editable
    assert body["status"] == {"state": state, "round": None}


# --- contact and source (US1) ----------------------------------------------------------------


def url(job_id: UUID, tail: str = "") -> str:
    return f"/api/v1/jobs/{job_id}/interview{tail}"


async def test_US1_AS2_contact_with_only_a_name(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"name": "Asha Rao"})

    assert response.status_code == 200
    assert response.json()["contact"] == {
        "name": "Asha Rao",
        "role": None,
        "email": None,
        "phone": None,
        "linkedin_url": None,
    }
    assert (await env.client.get(url(job_id))).json()["contact"]["name"] == "Asha Rao"


async def test_US1_contact_keeps_every_field_and_a_second_save_replaces_them(env: Env) -> None:
    job_id = await add_job(env)
    full = {
        "name": "Asha Rao",
        "role": "Recruiter",
        "email": "asha@example.com",
        "phone": "+91 98765 43210",
        "linkedin_url": "linkedin.com/in/asha",
    }
    await env.client.put(url(job_id, "/contact"), json=full)

    response = await env.client.put(url(job_id, "/contact"), json={"name": "Ben"})

    contact = response.json()["contact"]
    assert contact["name"] == "Ben"
    assert contact["role"] is None  # a save replaces every field
    first = await env.client.put(url(job_id, "/contact"), json=full)
    assert first.json()["contact"]["linkedin_url"] == "https://linkedin.com/in/asha"


async def test_US1_AS3_bad_email_refused(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(
        url(job_id, "/contact"), json={"name": "Asha", "email": "not-an-email"}
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["email"]
    assert (await env.client.get(url(job_id))).json()["contact"] is None  # nothing saved


async def test_US1_AS3_bad_linkedin_refused(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(
        url(job_id, "/contact"), json={"name": "Asha", "linkedin_url": "not a link"}
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["linkedin_url"]


async def test_US1_contact_needs_a_name(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"role": "Recruiter"})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["name"]


async def test_US1_clear_the_contact(env: Env) -> None:
    job_id = await add_job(env)
    await env.client.put(url(job_id, "/contact"), json={"name": "Asha"})
    await env.client.put(url(job_id, "/source"), json={"kind": "direct"})

    response = await env.client.delete(url(job_id, "/contact"))

    assert response.status_code == 200
    body = response.json()
    assert body["contact"] is None
    assert body["source"] == {"kind": "direct", "firm_name": None}  # the source stays


async def test_US1_AS4_hiring_firm_needs_a_name(env: Env) -> None:
    job_id = await add_job(env)

    refused = await env.client.put(url(job_id, "/source"), json={"kind": "hiring_firm"})
    saved = await env.client.put(
        url(job_id, "/source"), json={"kind": "hiring_firm", "firm_name": "TalentBridge"}
    )

    assert refused.status_code == 422
    assert [e["field"] for e in refused.json()["errors"]] == ["firm_name"]
    assert saved.json()["source"] == {"kind": "hiring_firm", "firm_name": "TalentBridge"}


async def test_US1_switch_to_direct_clears_the_firm(env: Env) -> None:
    job_id = await add_job(env)
    await env.client.put(
        url(job_id, "/source"), json={"kind": "hiring_firm", "firm_name": "TalentBridge"}
    )

    response = await env.client.put(
        url(job_id, "/source"), json={"kind": "direct", "firm_name": "Ignored"}
    )

    assert response.json()["source"] == {"kind": "direct", "firm_name": None}
    cleared = await env.client.put(url(job_id, "/source"), json={"kind": None})
    assert cleared.json()["source"] is None


async def test_US1_unknown_source_kind_refused(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/source"), json={"kind": "agency"})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["kind"]


@pytest.mark.parametrize("state", ["explore", "skipped"])
async def test_R6_not_in_pipeline_refused(env: Env, state: str) -> None:
    job_id = await add_job(env, state=state)

    contact = await env.client.put(url(job_id, "/contact"), json={"name": "Asha"})
    source = await env.client.put(url(job_id, "/source"), json={"kind": "direct"})
    clear = await env.client.delete(url(job_id, "/contact"))

    for response in (contact, source, clear):
        assert response.status_code == 409
        assert response.json()["reason"] == "not_in_pipeline"


async def test_US1_writes_to_an_unknown_job_are_404(env: Env) -> None:
    missing = UUID("00000000-0000-7000-8000-000000000999")

    assert (await env.client.put(url(missing, "/contact"), json={"name": "A"})).status_code == 404
    assert (await env.client.put(url(missing, "/source"), json={"kind": None})).status_code == 404


# --- review fixes -----------------------------------------------------------------------------


async def test_review_a_null_name_is_a_field_error(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"name": None})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["name"]


async def test_review_an_empty_kind_clears_the_source(env: Env) -> None:
    job_id = await add_job(env)
    await env.client.put(url(job_id, "/source"), json={"kind": "direct"})

    response = await env.client.put(url(job_id, "/source"), json={"kind": ""})

    assert response.status_code == 200
    assert response.json()["source"] is None


async def test_review_a_huge_field_is_refused_at_the_boundary(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"name": "x" * 5000})

    assert response.status_code == 422


async def test_review_saving_contact_and_source_at_once_both_work(env: Env) -> None:
    import asyncio

    job_id = await add_job(env)

    contact, source = await asyncio.gather(
        env.client.put(url(job_id, "/contact"), json={"name": "Asha Rao"}),
        env.client.put(
            url(job_id, "/source"), json={"kind": "hiring_firm", "firm_name": "TalentBridge"}
        ),
    )

    assert (contact.status_code, source.status_code) == (200, 200)
    body = (await env.client.get(url(job_id))).json()
    assert body["contact"]["name"] == "Asha Rao"
    assert body["source"] == {"kind": "hiring_firm", "firm_name": "TalentBridge"}


# --- US2: rounds -------------------------------------------------------------------------------

Body = dict[str, Any]
MISSING = "00000000-0000-0000-0000-000000000000"


async def add_round(env: Env, job_id: UUID, kind: str = "technical", **extra: object) -> Body:
    response = await env.client.post(url(job_id, "/rounds"), json={"kind": kind, **extra})
    assert response.status_code == 201, response.text
    body: Body = response.json()
    return body


def round_url(round_id: str) -> str:
    return f"/api/v1/interview/rounds/{round_id}"


async def test_US2_AS1_first_round_is_round_1_scheduled(env: Env) -> None:
    job_id = await add_job(env)

    body = await add_round(env, job_id, "technical", interviewers="Ben (EM)")

    assert [(r["number"], r["kind"], r["state"]) for r in body["rounds"]] == [
        (1, "technical", "scheduled")
    ]
    assert body["rounds"][0]["interviewers"] == "Ben (EM)"
    assert body["rounds"][0]["scheduled_at"] is None
    assert body["status"] == {"state": "scheduled", "round": 1}


async def test_US2_AS2_next_round_is_numbered_after(env: Env) -> None:
    job_id = await add_job(env)
    first = await add_round(env, job_id)
    await env.client.patch(round_url(first["rounds"][0]["id"]), json={"state": "cleared"})

    body = await add_round(env, job_id, "hr")

    assert [(r["number"], r["state"]) for r in body["rounds"]] == [(1, "cleared"), (2, "scheduled")]
    assert body["status"] == {"state": "scheduled", "round": 2}


async def test_US2_AS3_can_add_while_one_is_scheduled(env: Env) -> None:
    job_id = await add_job(env)
    await add_round(env, job_id)

    body = await add_round(env, job_id, "managerial")

    assert [r["number"] for r in body["rounds"]] == [1, 2]
    assert body["can_add_round"] is True


async def test_US2_AS4_failed_blocks_new_rounds(env: Env) -> None:
    job_id = await add_job(env)
    first = await add_round(env, job_id)
    patched = await env.client.patch(round_url(first["rounds"][0]["id"]), json={"state": "failed"})
    assert patched.json()["can_add_round"] is False
    assert patched.json()["status"] == {"state": "failed", "round": 1}

    response = await env.client.post(url(job_id, "/rounds"), json={"kind": "hr"})

    assert response.status_code == 409
    assert response.json()["reason"] == "process_failed"


async def test_US2_AS5_unfailing_allows_rounds_again(env: Env) -> None:
    job_id = await add_job(env)
    first = await add_round(env, job_id)
    round_id = first["rounds"][0]["id"]
    await env.client.patch(round_url(round_id), json={"state": "failed"})

    back = await env.client.patch(round_url(round_id), json={"state": "cleared"})
    assert back.json()["can_add_round"] is True

    body = await add_round(env, job_id, "hr")
    assert [r["number"] for r in body["rounds"]] == [1, 2]


async def test_US2_AS6_deleting_the_latest_round(env: Env) -> None:
    job_id = await add_job(env)
    await add_round(env, job_id)
    two = await add_round(env, job_id, "hr")
    await env.client.patch(round_url(two["rounds"][0]["id"]), json={"state": "cleared"})

    deleted = await env.client.delete(round_url(two["rounds"][1]["id"]))

    assert deleted.status_code == 200
    body = deleted.json()
    assert [r["number"] for r in body["rounds"]] == [1]
    assert body["status"] == {"state": "cleared", "round": 1}


async def test_US2_deleting_a_middle_round_keeps_the_other_numbers(env: Env) -> None:
    job_id = await add_job(env)
    await add_round(env, job_id)
    two = await add_round(env, job_id, "hr")
    await add_round(env, job_id, "managerial")

    deleted = await env.client.delete(round_url(two["rounds"][1]["id"]))

    assert [r["number"] for r in deleted.json()["rounds"]] == [1, 3]


async def test_US2_AS7_inquired_job_can_have_rounds(env: Env) -> None:
    job_id = await add_job(env, state="inquired")

    body = await add_round(env, job_id, "screening")

    assert body["status"] == {"state": "scheduled", "round": 1}


async def test_US2_AS8_past_date_on_scheduled_round(env: Env) -> None:
    job_id = await add_job(env)

    body = await add_round(env, job_id, scheduled_at="2020-01-02T10:30:00+05:30")

    assert body["rounds"][0]["state"] == "scheduled"
    assert body["rounds"][0]["scheduled_at"].startswith("2020-01-02T05:00:00")


async def test_US2_edit_kind_date_and_interviewers_then_clear_them(env: Env) -> None:
    job_id = await add_job(env)
    created = await add_round(env, job_id, interviewers="Ben")
    round_id = created["rounds"][0]["id"]

    edited = await env.client.patch(
        round_url(round_id),
        json={"kind": "hr", "scheduled_at": "2026-11-14T10:30:00Z", "interviewers": "Asha"},
    )
    assert edited.status_code == 200
    row = edited.json()["rounds"][0]
    assert (row["kind"], row["interviewers"]) == ("hr", "Asha")
    assert row["scheduled_at"].startswith("2026-11-14T10:30:00")

    cleared = await env.client.patch(
        round_url(round_id), json={"scheduled_at": None, "interviewers": ""}
    )
    row = cleared.json()["rounds"][0]
    assert (row["scheduled_at"], row["interviewers"]) == (None, None)
    assert row["kind"] == "hr"


async def test_unknown_kind_refused(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.post(url(job_id, "/rounds"), json={"kind": "coffee chat"})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["kind"]


async def test_bad_date_and_long_interviewers_refused(env: Env) -> None:
    job_id = await add_job(env)

    bad_date = await env.client.post(
        url(job_id, "/rounds"), json={"kind": "hr", "scheduled_at": "tomorrow-ish"}
    )
    too_long = await env.client.post(
        url(job_id, "/rounds"), json={"kind": "hr", "interviewers": "x" * 301}
    )

    assert bad_date.status_code == 422
    assert too_long.status_code == 422
    assert [e["field"] for e in too_long.json()["errors"]] == ["interviewers"]


async def test_unknown_state_on_patch_refused(env: Env) -> None:
    job_id = await add_job(env)
    created = await add_round(env, job_id)

    response = await env.client.patch(
        round_url(created["rounds"][0]["id"]), json={"state": "ghosted"}
    )

    assert response.status_code == 422


async def test_R6_round_refused_outside_the_pipeline(env: Env) -> None:
    job_id = await add_job(env, state="explore")

    response = await env.client.post(url(job_id, "/rounds"), json={"kind": "hr"})

    assert response.status_code == 409
    assert response.json()["reason"] == "not_in_pipeline"


async def test_R6_round_edit_refused_after_the_job_left_the_pipeline(env: Env) -> None:
    job_id = await add_job(env)
    created = await add_round(env, job_id)
    round_id = created["rounds"][0]["id"]
    async with env.sessions() as session:
        await JobsRepo(session).set_status(job_id, JobState.explore, None)
        await session.commit()

    patched = await env.client.patch(round_url(round_id), json={"state": "cleared"})
    deleted = await env.client.delete(round_url(round_id))

    assert (patched.status_code, deleted.status_code) == (409, 409)
    assert patched.json()["reason"] == "not_in_pipeline"


async def test_unknown_round_is_404(env: Env) -> None:
    patched = await env.client.patch(round_url(MISSING), json={"state": "cleared"})
    deleted = await env.client.delete(round_url(MISSING))
    unknown_job = await env.client.post(url(UUID(MISSING), "/rounds"), json={"kind": "hr"})

    assert (patched.status_code, deleted.status_code, unknown_job.status_code) == (404, 404, 404)


async def test_two_rounds_added_at_once_are_numbered_one_after_the_other(env: Env) -> None:
    import asyncio

    job_id = await add_job(env)

    first, second = await asyncio.gather(
        env.client.post(url(job_id, "/rounds"), json={"kind": "hr"}),
        env.client.post(url(job_id, "/rounds"), json={"kind": "technical"}),
    )

    assert (first.status_code, second.status_code) == (201, 201)
    body = (await env.client.get(url(job_id))).json()
    assert [r["number"] for r in body["rounds"]] == [1, 2]


# --- US3: questions, answers and feedback -----------------------------------------------------


def question_url(question_id: str) -> str:
    return f"/api/v1/interview/questions/{question_id}"


async def add_question(env: Env, round_id: str, question: str, **extra: object) -> Body:
    response = await env.client.post(
        f"/api/v1/interview/rounds/{round_id}/questions", json={"question": question, **extra}
    )
    assert response.status_code == 201, response.text
    body: Body = response.json()
    return body


async def a_round(env: Env) -> tuple[UUID, str]:
    job_id = await add_job(env)
    created = await add_round(env, job_id)
    return job_id, created["rounds"][0]["id"]


async def test_US3_AS1_question_without_answer_kept_in_order(env: Env) -> None:
    _, round_id = await a_round(env)
    await add_question(env, round_id, "Design a rate limiter")

    body = await add_question(env, round_id, "Explain CAP", answer="Pick two")

    questions = body["rounds"][0]["questions"]
    assert [(q["position"], q["question"], q["answer"]) for q in questions] == [
        (1, "Design a rate limiter", None),
        (2, "Explain CAP", "Pick two"),
    ]


async def test_US3_AS2_edit_or_delete_one_leaves_the_rest(env: Env) -> None:
    _, round_id = await a_round(env)
    await add_question(env, round_id, "One")
    await add_question(env, round_id, "Two")
    body = await add_question(env, round_id, "Three")
    one, two, three = (q["id"] for q in body["rounds"][0]["questions"])

    edited = await env.client.patch(question_url(two), json={"answer": "My answer"})
    answers = [q["answer"] for q in edited.json()["rounds"][0]["questions"]]
    assert answers == [None, "My answer", None]

    removed = await env.client.delete(question_url(one))

    assert removed.status_code == 200
    left = removed.json()["rounds"][0]["questions"]
    assert [(q["id"], q["question"]) for q in left] == [(two, "Two"), (three, "Three")]


async def test_US3_AS3_feedback_note_kept(env: Env) -> None:
    _, round_id = await a_round(env)

    saved = await env.client.patch(round_url(round_id), json={"feedback": "Good on design."})

    assert saved.json()["rounds"][0]["feedback"] == "Good on design."
    cleared = await env.client.patch(round_url(round_id), json={"feedback": ""})
    assert cleared.json()["rounds"][0]["feedback"] is None


async def test_US3_AS4_long_text_and_line_breaks_kept(env: Env) -> None:
    _, round_id = await a_round(env)
    question = "Line one\nLine two " + "q" * 1900
    answer = "a\n\nb " + "z" * 9000

    body = await add_question(env, round_id, question, answer=answer)
    feedback = "x" * 9990 + "\nend"
    saved = await env.client.patch(round_url(round_id), json={"feedback": feedback})

    stored = body["rounds"][0]["questions"][0]
    assert stored["question"] == question
    assert stored["answer"] == answer
    assert saved.json()["rounds"][0]["feedback"] == feedback


async def test_FR014_too_long_refused_with_the_limit(env: Env) -> None:
    _, round_id = await a_round(env)
    url_ = f"/api/v1/interview/rounds/{round_id}/questions"

    long_question = await env.client.post(url_, json={"question": "q" * 2001})
    long_answer = await env.client.post(url_, json={"question": "ok", "answer": "a" * 10001})
    long_feedback = await env.client.patch(round_url(round_id), json={"feedback": "f" * 10001})

    for response, field, limit in (
        (long_question, "question", "2000"),
        (long_answer, "answer", "10000"),
        (long_feedback, "feedback", "10000"),
    ):
        assert response.status_code == 422
        (error,) = response.json()["errors"]
        assert error["field"] == field
        assert limit in error["message"]


async def test_US3_a_question_needs_text(env: Env) -> None:
    _, round_id = await a_round(env)

    response = await env.client.post(
        f"/api/v1/interview/rounds/{round_id}/questions", json={"question": "   "}
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["question"]


async def test_US3_editing_a_question_cannot_empty_it(env: Env) -> None:
    _, round_id = await a_round(env)
    body = await add_question(env, round_id, "Keep me")
    question_id = body["rounds"][0]["questions"][0]["id"]

    response = await env.client.patch(question_url(question_id), json={"question": ""})
    cleared = await env.client.patch(question_url(question_id), json={"answer": None})

    assert response.status_code == 422
    assert cleared.status_code == 200


async def test_R6_questions_refused_after_the_job_left_the_pipeline(env: Env) -> None:
    job_id, round_id = await a_round(env)
    body = await add_question(env, round_id, "Asked")
    question_id = body["rounds"][0]["questions"][0]["id"]
    async with env.sessions() as session:
        await JobsRepo(session).set_status(job_id, JobState.explore, None)
        await session.commit()

    added = await env.client.post(
        f"/api/v1/interview/rounds/{round_id}/questions", json={"question": "More"}
    )
    patched = await env.client.patch(question_url(question_id), json={"answer": "x"})
    removed = await env.client.delete(question_url(question_id))

    assert (added.status_code, patched.status_code, removed.status_code) == (409, 409, 409)


async def test_unknown_question_or_round_is_404(env: Env) -> None:
    added = await env.client.post(
        f"/api/v1/interview/rounds/{MISSING}/questions", json={"question": "Q"}
    )
    patched = await env.client.patch(question_url(MISSING), json={"answer": "x"})
    removed = await env.client.delete(question_url(MISSING))

    assert (added.status_code, patched.status_code, removed.status_code) == (404, 404, 404)


async def test_questions_added_at_once_get_distinct_positions(env: Env) -> None:
    import asyncio

    _, round_id = await a_round(env)
    url_ = f"/api/v1/interview/rounds/{round_id}/questions"

    first, second = await asyncio.gather(
        env.client.post(url_, json={"question": "A"}),
        env.client.post(url_, json={"question": "B"}),
    )

    assert (first.status_code, second.status_code) == (201, 201)
    last = second.json() if len(second.json()["rounds"][0]["questions"]) == 2 else first.json()
    assert sorted(q["position"] for q in last["rounds"][0]["questions"]) == [1, 2]


# --- T020 final review fixes --------------------------------------------------------------------


async def test_review_a_link_that_is_too_long_once_https_is_added_is_a_field_error(
    env: Env,
) -> None:
    job_id = await add_job(env)
    # 500 characters as typed, 508 once "https://" is put in front of the bare host
    link = "linkedin.com/in/" + "a" * 484

    response = await env.client.put(
        url(job_id, "/contact"), json={"name": "Asha", "linkedin_url": link}
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["linkedin_url"]


async def test_review_contact_save_waits_for_a_delete_in_flight(env: Env) -> None:
    import asyncio

    from hiretitan.search.infra.interviews_repo import InterviewsRepo
    from hiretitan.search.infra.models import JobRow, PipelineDetailsRow

    job_id = await add_job(env)
    holding = asyncio.Event()

    async def delete_slowly() -> None:
        async with env.sessions() as session:
            await InterviewsRepo(session).lock_job(job_id)
            holding.set()
            await asyncio.sleep(0.3)
            row = await session.get_one(JobRow, job_id)
            row.state = "deleted"
            row.applied_on = None
            await InterviewsRepo(session).delete_for_job(job_id)
            await session.commit()

    deleting = asyncio.create_task(delete_slowly())
    await holding.wait()
    response = await env.client.put(url(job_id, "/contact"), json={"name": "Asha Rao"})
    await deleting

    assert response.status_code == 404
    async with env.sessions() as session:
        assert await session.get(PipelineDetailsRow, job_id) is None
