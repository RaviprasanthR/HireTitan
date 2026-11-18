"""Tailored resume endpoints (T024, T025): US4, FR-009, FR-016, FR-017, FR-018, FR-019, EC-06."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from docx import Document
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import KEYWORDS, DraftsEnv, make_env

from hiretitan.api_main import create_app
from hiretitan.drafts.api.drafts import DraftsApiDeps
from hiretitan.drafts.api.resumes import create_resumes_router, safe_filename
from hiretitan.drafts.infra.repos import TailoredRepo
from hiretitan.drafts.workflow.tailor import run_tailor
from hiretitan.drafts_wiring import SqlContacts
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Api:
    client: httpx.AsyncClient
    env: DraftsEnv
    queue: Queue

    @property
    def url(self) -> str:
        return f"/api/v1/jobs/{self.env.job_id}/tailored-resume"


def build(
    env: DraftsEnv, sessions: async_sessionmaker[AsyncSession], tmp: Path, queue: Queue
) -> httpx.AsyncClient:
    deps = DraftsApiDeps(
        sessions=sessions,
        queue=queue,
        jobs=env.deps.jobs,
        profile=env.deps.profile,
        contacts=SqlContacts(sessions),
        provider="fake",
    )
    app = create_app(Settings(), frontend_dist=tmp / "none", routers=[create_resumes_router(deps)])
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


from hiretitan.platform.config.settings import Settings  # noqa: E402


@pytest.fixture
async def api(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Api]:
    env = await make_env(sessions)
    queue = Queue()
    async with build(env, sessions, tmp_path, queue) as client:
        yield Api(client, env, queue)


async def tailored(api: Api) -> None:
    """Start the resume through the API and let the workflow finish it."""
    started = await api.client.post(api.url, json={})
    assert started.status_code == 202
    run_id = api.queue.enqueued[-1]
    profile = await api.env.deps.profile.current()
    assert profile is not None
    newest = profile.view.experience[0]
    api.env.llm.add(KEYWORDS, task="extract_job_keywords")
    api.env.llm.add(
        {
            "summary": "Backend engineer who builds reliable Python APIs.",
            "experience": [
                {
                    "experience_id": newest.id,
                    "bullets": [
                        {"source_index": 1, "text": "Moved a PostgreSQL schema to partitions"}
                    ],
                }
            ],
            "skills": ["Python"],
            "project_ids": [],
        },
        task="tailor_resume",
    )
    await run_tailor(api.env.deps, run_id, api.env.job_id)


async def test_FR019_no_description_refused(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    env = await make_env(sessions, description="Too short.")
    async with build(env, sessions, tmp_path, Queue()) as client:
        res = await client.post(f"/api/v1/jobs/{env.job_id}/tailored-resume", json={})

    assert res.status_code == 409
    assert res.json()["reason"] == "no_description"


async def test_US4_AS1_start_then_get_shows_writing_then_ready(api: Api) -> None:
    assert (await api.client.get(api.url)).status_code == 404

    started = await api.client.post(api.url, json={})
    writing = (await api.client.get(api.url)).json()

    assert started.json() == {"job_id": str(api.env.job_id), "status": "writing"}
    assert writing["status"] == "writing"
    assert writing["document"] is None
    assert (await api.client.post(api.url, json={})).json()["reason"] == "resume_in_progress"
    assert len(api.queue.enqueued) == 1


async def test_FR016_person_edits_kept(api: Api) -> None:
    await tailored(api)
    current = (await api.client.get(api.url)).json()
    assert current["status"] == "ready"
    doc = current["document"]
    doc["summary"] = "My own summary of Python and Django work."
    doc["experience"][0]["bullets"] = ["Hand written bullet about Kubernetes"]  # not checked

    saved = await api.client.put(api.url, json={"document": doc})

    assert saved.status_code == 200
    assert saved.json()["edited"] is True
    assert saved.json()["document"]["summary"] == "My own summary of Python and Django work."
    again = (await api.client.post(api.url, json={})).json()  # a ready resume is returned as is
    assert again["document"]["experience"][0]["bullets"] == ["Hand written bullet about Kubernetes"]
    bad = await api.client.put(api.url, json={"document": {"summary": "x"}})
    assert bad.status_code == 422
    huge = dict(doc, summary="s" * 1201)
    assert (await api.client.put(api.url, json={"document": huge})).status_code == 422


async def test_FR017_match_recomputed_on_save(api: Api) -> None:
    await tailored(api)
    current = (await api.client.get(api.url)).json()
    before = set(current["keyword_match"]["matched"])
    doc = current["document"]
    doc["skills"] = []
    doc["summary"] = ""
    doc["experience"] = []
    doc["projects"] = []

    saved = (await api.client.put(api.url, json={"document": doc})).json()

    assert "Python" in before
    assert saved["keyword_match"]["matched"] == []
    reasons = {m["keyword"]: m["reason"] for m in saved["keyword_match"]["missing"]}
    assert reasons["Python"] == "not_in_resume"  # the profile has it, the resume does not
    assert reasons["REST"] == "not_in_profile"


async def test_FR019_listed_for_profile_page(api: Api) -> None:
    assert (await api.client.get("/api/v1/tailored-resumes")).json() == []
    await tailored(api)

    items = (await api.client.get("/api/v1/tailored-resumes")).json()

    assert [(i["job_id"], i["job_title"], i["company"]) for i in items] == [
        (str(api.env.job_id), "Backend Engineer", "Acme")
    ]


async def test_FR009_delete_tailored_resume(api: Api) -> None:
    await api.client.post(api.url, json={})
    assert (await api.client.delete(api.url)).status_code == 409  # still writing
    async with api.env.sessions() as session:
        await TailoredRepo(session).set_failed(api.env.job_id, "x")
        await session.commit()

    assert (await api.client.delete(api.url)).status_code == 204
    missing = await api.client.delete(api.url)
    assert missing.status_code == 404
    assert missing.json()["reason"] == "not_tailored"


async def test_FR018_download_404_when_not_ready(api: Api) -> None:
    assert (await api.client.get(api.url + ".pdf")).status_code == 404
    await api.client.post(api.url, json={})
    assert (await api.client.get(api.url + ".docx")).status_code == 404


async def test_FR018_download_pdf_and_docx(api: Api) -> None:
    await tailored(api)

    pdf = await api.client.get(api.url + ".pdf")
    docx = await api.client.get(api.url + ".docx")

    assert pdf.status_code == docx.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"
    assert (
        'filename="Sam Rivera - Acme - Backend Engineer.pdf"' in pdf.headers["content-disposition"]
    )
    paragraphs = [p.text for p in Document(BytesIO(docx.content)).paragraphs]
    assert "Sam Rivera" in paragraphs
    assert "Experience" in paragraphs


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (
            ("Zoë Çelik", "Ac/me\r\nInc", 'Role "x"; rm -rf'),
            "Zoe Celik - Ac me Inc - Role x rm -rf",
        ),
        (("../../etc/passwd", "", ""), "etc passwd"),
        (("名字", "", ""), "resume"),
        (("a" * 300,), "a" * 100),
    ],
)
def test_EC13_download_filename_is_safe(parts: tuple[str, ...], expected: str) -> None:
    name = safe_filename(*parts)

    assert name == expected
    assert not set(name) & set('/\\\r\n";:')


async def test_EC06_resume_in_progress_409(api: Api) -> None:
    await api.client.post(api.url, json={})

    res = await api.client.post(api.url, json={"regenerate": True})

    assert res.status_code == 409
    assert res.json()["reason"] == "resume_in_progress"
    async with api.env.sessions() as session:
        assert await RunsRepo(session).get(api.queue.enqueued[0]) is not None


async def test_EC06_two_tailor_clicks_at_once_give_one_run_and_one_409(api: Api) -> None:
    import asyncio

    url = f"/api/v1/jobs/{api.env.job_id}/tailored-resume"
    first, second = await asyncio.gather(
        api.client.post(url, json={}), api.client.post(url, json={})
    )
    assert sorted([first.status_code, second.status_code]) == [202, 409]


async def test_EC13_control_characters_in_an_edit_do_not_break_the_download(api: Api) -> None:
    await tailored(api)
    doc = (await api.client.get(api.url)).json()["document"]
    doc["summary"] = "Python\x00 and\x0b Django\x1f work."

    saved = await api.client.put(api.url, json={"document": doc})

    assert saved.status_code == 200
    assert saved.json()["document"]["summary"] == "Python and Django work."
    assert (await api.client.get(api.url + ".docx")).status_code == 200
    assert (await api.client.get(api.url + ".pdf")).status_code == 200
