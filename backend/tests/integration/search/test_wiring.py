"""T033: the search module's composition roots (career-ops choice, seed at start-up, registry)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.config.settings import Settings
from hiretitan.search.application.ports import BoardRef, ScanError, ScanOk
from hiretitan.search.infra.careerops.adapter import CareerOpsAdapter
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.models import CompanyRow
from hiretitan.search.workflow.graph import WORKFLOW_NAME as SEARCH_WORKFLOW
from hiretitan.search_wiring import build_career_ops, seed_companies
from hiretitan.worker_main import workflow_registry


def test_career_ops_setting_defaults_to_real() -> None:
    settings = Settings()
    assert settings.career_ops == "real"
    assert settings.fake_career_ops_dir is None


def test_career_ops_setting_reads_the_environment(tmp_path: Path) -> None:
    settings = Settings(HIRETITAN_CAREER_OPS="fake", HIRETITAN_FAKE_CAREER_OPS_DIR=str(tmp_path))
    assert (settings.career_ops, settings.fake_career_ops_dir) == ("fake", tmp_path)


def test_real_mode_builds_the_adapter_and_fake_mode_the_file_fake(tmp_path: Path) -> None:
    real = build_career_ops(Settings(HIRETITAN_DATA_DIR=str(tmp_path)))
    fake = build_career_ops(Settings(HIRETITAN_CAREER_OPS="fake"))
    assert isinstance(real, CareerOpsAdapter)
    assert isinstance(fake, FileCareerOps)


async def test_file_fake_answers_from_json_files(tmp_path: Path) -> None:
    (tmp_path / "lever__acme.json").write_text(
        json.dumps(
            {
                "postings": [
                    {
                        "title": "Backend Engineer",
                        "url": "https://jobs.example.com/acme/1",
                        "location": "Pune, India",
                        "posted_at": "2026-11-01T00:00:00+00:00",
                        "description": "Python.",
                    }
                ]
            }
        ),
        "utf-8",
    )
    (tmp_path / "lever__broken.json").write_text(json.dumps({"error": "timed out"}), "utf-8")
    fake = FileCareerOps(tmp_path)
    ids = [BoardRef(c, "lever", b) for c, b in (("a", "acme"), ("b", "broken"), ("c", "none"))]
    refs = [BoardRef(__import__("uuid").uuid4(), r.vendor, r.board_id) for r in ids]

    result: dict[Any, Any] = await fake.scan(refs)

    ok = result[refs[0].company_id]
    assert isinstance(ok, ScanOk)
    assert (ok.postings[0].title, ok.postings[0].posted_at.year) == ("Backend Engineer", 2026)  # type: ignore[union-attr]
    assert result[refs[1].company_id] == ScanError("timed out")
    assert result[refs[2].company_id] == ScanOk([])  # no file: no jobs


async def test_seed_companies_loads_the_shipped_list(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    path = tmp_path / "companies.yaml"
    path.write_text(
        "- {key: acme, name: Acme, resolution: verified, seed_version: 1,"
        " ats_vendor: lever, board_id: acme}\n",
        "utf-8",
    )

    first = await seed_companies(sessions, path)
    second = await seed_companies(sessions, path)

    assert first is not None
    assert (first.inserted, second.inserted if second else -1) == (1, 0)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(CompanyRow)) == 1


async def test_seed_companies_without_a_file_does_nothing(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    assert await seed_companies(sessions, tmp_path / "missing.yaml") is None


def test_job_search_registered() -> None:
    registry = workflow_registry(MagicMock(), MagicMock())
    assert SEARCH_WORKFLOW in registry
    assert registry[SEARCH_WORKFLOW].recursion_limit > 25
