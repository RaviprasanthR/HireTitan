"""The tailor workflow (T024): US4, FR-007, FR-015, FR-017."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import KEYWORDS, DraftsEnv, make_env

from hiretitan.drafts.domain.resume_doc import ResumeDocument
from hiretitan.drafts.infra.models import TailoredResumeRow
from hiretitan.drafts.infra.repos import TailoredRepo
from hiretitan.drafts.workflow.tailor import TAILOR_WORKFLOW, run_tailor
from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession]) -> DraftsEnv:
    return await make_env(sessions)


async def begin(env: DraftsEnv) -> UUID:
    async with env.sessions() as session:
        await TailoredRepo(session).start_writing(env.job_id)
        run = await RunsRepo(session).create(TAILOR_WORKFLOW, subject_id=env.job_id)
        await TailoredRepo(session).set_run(env.job_id, run.id)
        await session.commit()
        return run.id


async def stored(env: DraftsEnv) -> TailoredResumeRow:
    async with env.sessions() as session:
        row = await TailoredRepo(session).get_for_job(env.job_id)
    assert row is not None
    return row


async def good_answer(env: DraftsEnv) -> dict[str, Any]:
    profile = await env.deps.profile.current()
    assert profile is not None
    newest = profile.view.experience[0]
    return {
        "summary": "Backend engineer who builds reliable Python APIs on PostgreSQL.",
        "experience": [
            {
                "experience_id": newest.id,
                "bullets": [
                    {"source_index": 1, "text": "Moved a PostgreSQL schema to partitioned tables"},
                    {
                        "source_index": 0,
                        "text": "Built a Python service handling 40 requests per second",
                    },
                ],
            }
        ],
        "skills": ["PostgreSQL", "Python"],
        "project_ids": [],
    }


async def test_US4_AS1_tailored_resume_ready(env: DraftsEnv) -> None:
    run_id = await begin(env)
    env.llm.add(KEYWORDS, task="extract_job_keywords")
    env.llm.add(await good_answer(env), task="tailor_resume")

    await run_tailor(env.deps, run_id, env.job_id)

    row = await stored(env)
    assert row.status == "ready"
    assert row.source == "ai"
    assert row.prompt_name == "tailor_resume"
    assert row.profile_version_id is not None
    assert row.keyword_match is not None
    assert "Python" in row.keyword_match["matched"]
    request = next(c for c in env.llm.calls if c.task == "tailor_resume")
    assert request.tier == "strong"
    assert ("tailored_resume.ready", {"job_id": str(env.job_id)}) in env.published


async def test_FR015_tailored_resume_keeps_every_fact(env: DraftsEnv) -> None:
    run_id = await begin(env)
    env.llm.add(KEYWORDS, task="extract_job_keywords")
    env.llm.add(await good_answer(env), task="tailor_resume")
    await run_tailor(env.deps, run_id, env.job_id)

    row = await stored(env)
    doc = ResumeDocument.model_validate(row.document)
    profile = await env.deps.profile.current()
    assert profile is not None
    assert [(e.employer, e.title) for e in doc.experience] == [
        (j.employer, j.title) for j in profile.view.experience
    ]
    assert doc.experience[0].bullets[0].startswith("Moved a PostgreSQL")  # reordered, same words
    assert doc.experience[1].bullets == list(profile.view.experience[1].bullets)
    assert set(doc.skills) == set(profile.view.skills)
    assert doc.contact.name == profile.view.contact.name
    assert [e.institution for e in doc.education] == ["Lakeside University"]


async def test_US4_AS2_repair_then_plain_reorder(env: DraftsEnv) -> None:
    run_id = await begin(env)
    bad = {
        "summary": "Led 12 engineers at Globex using Kubernetes.",
        "experience": [],
        "skills": ["Python"],
        "project_ids": [],
    }
    env.llm.add(KEYWORDS, task="extract_job_keywords")
    env.llm.add(bad, bad, task="tailor_resume")

    await run_tailor(env.deps, run_id, env.job_id)

    row = await stored(env)
    assert row.status == "ready"
    assert row.source == "fallback"
    assert row.prompt_name is None
    assert "Globex" not in str(row.document)
    assert "Backend engineer who builds reliable APIs in Python." in str(row.document)


async def test_FR007_out_of_credit_pauses_tailoring(env: DraftsEnv) -> None:
    run_id = await begin(env)
    env.llm.add(AiUnavailable("out_of_credit", "quota"), task="extract_job_keywords")

    with pytest.raises(AiUnavailable):
        await run_tailor(env.deps, run_id, env.job_id)
    assert (await stored(env)).status == "writing"

    env.llm.add(KEYWORDS, task="extract_job_keywords")
    env.llm.add(await good_answer(env), task="tailor_resume")
    await run_tailor(env.deps, run_id, env.job_id)

    assert (await stored(env)).status == "ready"


async def test_FR019_short_description_fails_without_calling_the_ai(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    env = await make_env(sessions, description="Too short.")
    run_id = await begin(env)

    await run_tailor(env.deps, run_id, env.job_id)

    row = await stored(env)
    assert row.status == "failed"
    assert "description" in (row.failure_reason or "")
    assert env.llm.calls == []


async def test_FR014_no_profile_fails(sessions: async_sessionmaker[AsyncSession]) -> None:
    env = await make_env(sessions, with_profile=False)
    run_id = await begin(env)

    await run_tailor(env.deps, run_id, env.job_id)

    row = await stored(env)
    assert row.status == "failed"
    assert "profile" in (row.failure_reason or "")
    assert any(event == "tailored_resume.failed" for event, _ in env.published)


async def test_FR013_a_run_that_fails_marks_the_resume_failed(env: DraftsEnv) -> None:
    from hiretitan.drafts.infra.repos import TailoredRepo
    from hiretitan.drafts.workflow.tailor import TAILOR_WORKFLOW, WENT_WRONG, tailor_workflow
    from hiretitan.platform.runtime.infra.runs_repo import RunsRepo

    async with env.sessions() as session:
        await TailoredRepo(session).start_writing(env.job_id)
        run = await RunsRepo(session).create(TAILOR_WORKFLOW, subject_id=env.job_id)
        await session.commit()
    hook = tailor_workflow(env.deps).on_failed
    assert hook is not None
    await hook(run)
    async with env.sessions() as session:
        saved = await TailoredRepo(session).get_for_job(env.job_id)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.failure_reason == WENT_WRONG
