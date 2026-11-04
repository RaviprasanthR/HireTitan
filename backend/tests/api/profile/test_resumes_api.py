"""T042: uploading and pasting a resume (FR-001, FR-002, FR-003)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.profile.api.resumes import ProfileApiDeps, create_resumes_router
from hiretitan.profile.infra.repos import Provenance, ResumeFilesRepo, ReviewsRepo

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "resumes"
MAX_BYTES = 10_485_760


@dataclass
class FakeQueue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Env:
    client: httpx.AsyncClient
    queue: FakeQueue
    storage: LocalFileStorage
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    queue = FakeQueue()
    storage = LocalFileStorage(tmp_path / "data")
    deps = ProfileApiDeps(sessions=sessions, storage=storage, queue=queue)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_resumes_router(deps)]
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Env(client, queue, storage, sessions)


def pdf_upload(name: str = "synthetic-mid-2page.pdf", filename: str | None = None):  # type: ignore[no-untyped-def]
    data = (FIXTURES / name).read_bytes()
    return {"file": (filename or name, data, "application/octet-stream")}, data


async def test_FR001_upload_pdf_accepted_202(env: Env) -> None:
    files, data = pdf_upload()
    response = await env.client.post("/api/v1/resumes", files=files)

    assert response.status_code == 202
    body = response.json()
    file_id, run_id = UUID(body["resume_file_id"]), UUID(body["run_id"])
    assert env.queue.enqueued == [run_id]

    async with env.sessions() as session:
        stored = await ResumeFilesRepo(session).get(file_id)
        run = await RunsRepo(session).get(run_id)
    assert stored is not None
    assert (stored.kind, stored.original_name, stored.size_bytes) == (
        "upload_pdf",
        "synthetic-mid-2page.pdf",
        len(data),
    )
    assert stored.page_count == 2
    assert run is not None
    assert (run.workflow, run.subject_id, run.state.status) == (
        "profile_ingest",
        file_id,
        RunStatus.queued,
    )


async def test_docx_upload_is_accepted(env: Env) -> None:
    files, _ = pdf_upload("synthetic-fresher.docx")
    response = await env.client.post("/api/v1/resumes", files=files)
    assert response.status_code == 202
    async with env.sessions() as session:
        [stored] = await ResumeFilesRepo(session).list()
    assert (stored.kind, stored.page_count) == ("upload_docx", None)


async def test_FR003_file_kept_unchanged(env: Env) -> None:
    files, data = pdf_upload()
    await env.client.post("/api/v1/resumes", files=files)
    async with env.sessions() as session:
        [stored] = await ResumeFilesRepo(session).list()
    assert env.storage.get(stored.sha256) == data


async def test_filename_is_reduced_to_its_base_name(env: Env) -> None:
    files, _ = pdf_upload(filename="C:\\Users\\jane\\docs\\my resume.pdf")
    await env.client.post("/api/v1/resumes", files=files)
    async with env.sessions() as session:
        [stored] = await ResumeFilesRepo(session).list()
    assert stored.original_name == "my resume.pdf"


async def test_FR001_wrong_type_415(env: Env) -> None:
    files = {"file": ("resume.pdf", b"MZ\x90\x00" + b"\x00" * 300, "application/pdf")}
    response = await env.client.post("/api/v1/resumes", files=files)
    assert response.status_code == 415
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "Only PDF and DOCX files are supported"
    assert env.queue.enqueued == []


async def test_old_doc_gets_the_specific_message(env: Env) -> None:
    files = {"file": ("old.doc", bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 512, "x/y")}
    response = await env.client.post("/api/v1/resumes", files=files)
    assert response.status_code == 415
    assert "password-protected or old .doc" in response.json()["detail"]


async def test_FR001_too_large_413(env: Env) -> None:
    files = {"file": ("big.pdf", b"%PDF-1.7\n" + b"x" * MAX_BYTES, "application/pdf")}
    response = await env.client.post("/api/v1/resumes", files=files)
    assert response.status_code == 413
    assert response.json()["detail"] == "The file is larger than 10 MB"
    assert env.queue.enqueued == []


async def test_encrypted_and_corrupt_files_are_422(env: Env) -> None:
    files, _ = pdf_upload("synthetic-encrypted.pdf")
    assert (await env.client.post("/api/v1/resumes", files=files)).status_code == 422
    bad = {"file": ("x.docx", b"PK\x03\x04" + b"junk" * 50, "x/y")}
    assert (await env.client.post("/api/v1/resumes", files=bad)).status_code == 422


async def test_missing_file_field_is_422(env: Env) -> None:
    response = await env.client.post("/api/v1/resumes")
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "file"


PASTED = "Jane Example. " + "Backend engineer with six years of experience in Python and Go. " * 5


async def test_FR002_paste_text_accepted(env: Env) -> None:
    response = await env.client.post("/api/v1/resumes/text", json={"text": PASTED})
    assert response.status_code == 202
    file_id = UUID(response.json()["resume_file_id"])
    async with env.sessions() as session:
        stored = await ResumeFilesRepo(session).get(file_id)
    assert stored is not None
    assert (stored.kind, stored.original_name) == ("pasted_text", "pasted text")
    assert stored.size_bytes == len(PASTED.encode())
    assert env.storage.get(stored.sha256) == PASTED.encode()
    assert env.queue.enqueued == [UUID(response.json()["run_id"])]


@pytest.mark.parametrize("length", [199, 60_001])
async def test_pasted_text_length_is_bounded(env: Env, length: int) -> None:
    response = await env.client.post("/api/v1/resumes/text", json={"text": "x" * length})
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "text"


async def test_pasted_text_bounds_are_inclusive(env: Env) -> None:
    for length in (200, 60_000):
        response = await env.client.post("/api/v1/resumes/text", json={"text": "x" * length})
        assert response.status_code == 202


async def open_review(env: Env) -> tuple[UUID, UUID]:
    """An existing open review and its (awaiting_review) run."""
    async with env.sessions() as session:
        file = await ResumeFilesRepo(session).create(
            kind="upload_pdf", original_name="old.pdf", size_bytes=10, sha256="c" * 64
        )
        runs = RunsRepo(session)
        run = await runs.create("profile_ingest", subject_id=file.id)
        await runs.transition(run.id, RunStatus.running)
        await runs.transition(
            run.id,
            RunStatus.awaiting_review,
            waiting_for=__import__(
                "hiretitan.platform.runtime.domain.run_state", fromlist=["WaitingFor"]
            ).WaitingFor.profile_review,
        )
        review = await ReviewsRepo(session).create(
            run_id=run.id,
            resume_file_id=file.id,
            extraction={},
            dropped_items=[],
            flags={},
            provenance=Provenance("extract_profile", "1", "fake", "m"),
        )
        await session.commit()
    return review.id, run.id


async def test_edge_case_second_upload_conflicts_while_review_open(env: Env) -> None:
    review_id, _ = await open_review(env)
    files, _ = pdf_upload()
    response = await env.client.post("/api/v1/resumes", files=files)

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["open_review_id"] == str(review_id)
    assert env.queue.enqueued == []
    async with env.sessions() as session:
        assert len(await ResumeFilesRepo(session).list()) == 1  # nothing new was stored


async def test_discard_open_review_flag_replaces_the_review(env: Env) -> None:
    review_id, old_run_id = await open_review(env)
    files, _ = pdf_upload()
    response = await env.client.post("/api/v1/resumes?discard_open_review=true", files=files)

    assert response.status_code == 202
    async with env.sessions() as session:
        old_review = await ReviewsRepo(session).get(review_id)
        old_run = await RunsRepo(session).get(old_run_id)
    assert old_review is not None
    assert old_review.status == "discarded"
    assert old_run is not None
    assert old_run.state.status is RunStatus.cancelled


async def test_pasted_text_also_conflicts_while_review_open(env: Env) -> None:
    await open_review(env)
    response = await env.client.post("/api/v1/resumes/text", json={"text": PASTED})
    assert response.status_code == 409


async def test_get_resumes_lists_files_with_open_review_flag(env: Env) -> None:
    assert (await env.client.get("/api/v1/resumes")).json() == []
    review_id, _ = await open_review(env)
    items = (await env.client.get("/api/v1/resumes")).json()
    assert len(items) == 1
    item = items[0]
    assert item["original_name"] == "old.pdf"
    assert item["kind"] == "upload_pdf"
    assert item["has_open_review"] is True
    assert item["open_review_id"] == str(review_id)
    assert item["parse_result"] is None  # the workflow has not parsed it yet
    assert {"id", "size_bytes", "created_at", "parse_status"} <= set(item)
    assert UUID(item["id"])
    assert review_id


async def test_plan_10mb_upload_accepted_under_2s(env: Env) -> None:
    base = (FIXTURES / "synthetic-mid-2page.pdf").read_bytes()
    padded = base + b"\n%" + b"p" * (MAX_BYTES - len(base) - 2)
    assert len(padded) == MAX_BYTES
    started = time.perf_counter()
    response = await env.client.post(
        "/api/v1/resumes", files={"file": ("big.pdf", padded, "application/pdf")}
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == 202
    assert elapsed < 2.0, f"took {elapsed:.2f}s"


async def test_no_stray_rows_after_a_rejected_upload(env: Env) -> None:
    await env.client.post("/api/v1/resumes", files={"file": ("x.pdf", b"nope", "x/y")})
    async with env.sessions() as session:
        files = (await session.execute(text("SELECT count(*) FROM app.resume_files"))).scalar_one()
        runs = (await session.execute(text("SELECT count(*) FROM app.workflow_runs"))).scalar_one()
    assert (files, runs) == (0, 0)
