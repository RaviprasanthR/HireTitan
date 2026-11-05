"""Helpers for the profile_ingest workflow tests: a real database, storage, parsers and graph,
with a scripted fake LLM that records every prompt it receives."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.runtime.domain.run_state import RunState
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.runtime.runner import WorkflowRunner, resume_run
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.profile.application.ingest import ingest_file, ingest_text
from hiretitan.profile.infra.ingest_store import SqlIngestStore
from hiretitan.profile.infra.parsing.sniff import sniff
from hiretitan.profile.infra.repos import ResumeFile, ResumeFilesRepo, Review, ReviewsRepo
from hiretitan.profile.workflow.graph import IngestDeps

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "resumes"
PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"


def jane_extraction(**overrides: Any) -> dict[str, Any]:
    """What a good model returns for synthetic-mid-2page.pdf."""
    base: dict[str, Any] = {
        "looks_like_resume": True,
        "contact": {"name": "Jane Example", "location": "Pune, India"},
        "headline": None,
        "summary": (
            "Backend engineer with six years of experience building data pipelines and APIs."
        ),
        "experience": [
            {
                "employer": "Acme Corp",
                "title": "Senior Software Engineer",
                "location": None,
                "start": {"year": 2021, "month": 1},
                "end": None,
                "current": True,
                "bullets": ["Led a team of 5 engineers on the billing platform migration"],
            },
            {
                "employer": "Globex Ltd",
                "title": "Software Engineer",
                "location": None,
                "start": {"year": 2017, "month": 6},
                "end": {"year": 2020, "month": 12},
                "current": False,
                "bullets": ["Built REST APIs in Python serving 2M requests per day"],
            },
        ],
        "education": [
            {
                "institution": "Example Institute of Technology",
                "qualification": "B.Tech Computer Science",
                "field": None,
                "start": {"year": 2013, "month": None},
                "end": {"year": 2017, "month": None},
                "grade": None,
            }
        ],
        "skills": ["Python", "Go", "PostgreSQL", "C++", "Node.js"],
        "projects": [{"name": "Tracer", "description": None, "technologies": ["Rust"]}],
        "certifications": [{"name": "AWS Certified Developer", "issuer": None, "date": None}],
    }
    base.update(overrides)
    return base


@dataclass
class Harness:
    sessions: async_sessionmaker[AsyncSession]
    storage: LocalFileStorage
    llm: FakeLlm
    runner: WorkflowRunner
    deps: IngestDeps
    published: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def start(self, fixture: str | None = None, *, text_: str | None = None) -> UUID:
        """Accept a resume exactly like the API does, and return the queued run's id."""

        class _Queue:
            async def enqueue(self, run_id: UUID, resume: object = None) -> None:
                return None

        async with self.sessions() as session:
            store = SqlIngestStore(session)
            if fixture is not None:
                accepted = await ingest_file(
                    data=(FIXTURES / fixture).read_bytes(),
                    filename=fixture,
                    inspect=lambda data: _inspected(data),
                    storage=self.storage,
                    store=store,
                    queue=_Queue(),
                    discard_open_review=True,
                )
            else:
                accepted = await ingest_text(
                    text=text_ or "",
                    storage=self.storage,
                    store=store,
                    queue=_Queue(),
                    discard_open_review=True,
                )
        return accepted.run_id

    async def run(self, run_id: UUID, **kwargs: Any) -> RunState:
        await self.runner.execute(run_id, **kwargs)
        return await self.state(run_id)

    async def resume(self, run_id: UUID, value: Any) -> RunState:
        """What the API does when the user answers: re-queue the run, then run the job."""

        class _Queue:
            async def enqueue(self, run_id: UUID, resume: object = None) -> None:
                return None

        await resume_run(self.sessions, _Queue(), run_id, value)
        return await self.run(run_id, resume=value)

    async def state(self, run_id: UUID) -> RunState:
        async with self.sessions() as session:
            run = await RunsRepo(session).get(run_id)
        assert run is not None
        return run.state

    async def review(self) -> Review | None:
        async with self.sessions() as session:
            return await ReviewsRepo(session).get_open()

    async def file_for(self, run_id: UUID) -> ResumeFile:
        async with self.sessions() as session:
            run = await RunsRepo(session).get(run_id)
            assert run is not None
            assert run.subject_id is not None
            file = await ResumeFilesRepo(session).get(run.subject_id)
        assert file is not None
        return file

    async def count(self, sql: str) -> int:
        async with self.sessions() as session:
            return int((await session.execute(text(sql))).scalar_one())

    def prompt_text(self) -> str:
        """Everything the fake LLM was sent, joined."""
        return "\n".join(
            "\n".join([c.prompt.system, c.prompt.user, *(b.text for b in c.untrusted_blocks)])
            for c in self.llm.calls
        )


def _inspected(data: bytes):  # type: ignore[no-untyped-def]
    from hiretitan.profile.application.ingest import Inspected

    sniffed = sniff(data)
    return Inspected(sniffed.kind, sniffed.page_count)
