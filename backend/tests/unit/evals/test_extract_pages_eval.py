"""T053: the careers-page eval set and runner. Uses FakeLlm: no network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from evals.extract_jobs_from_page.cases import CASES, EVIL
from evals.extract_jobs_from_page.runner import (
    evaluate_pages,
    render_pages_report,
    score_page,
)
from evals.run import main

from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.search.infra.careers_page.parse import parse_careers_page
from hiretitan.search.infra.careers_page.text import page_text


def perfect() -> list[dict[str, Any]]:
    return [{"jobs": [{"title": t, "url": u} for t, u in case.jobs]} for case in CASES]


def test_ten_pages_with_unique_ids_and_hosts() -> None:
    assert len(CASES) == 10
    assert len({c.id for c in CASES}) == 10
    assert len({c.host for c in CASES}) == 10


def test_every_labelled_job_and_link_is_really_on_its_page() -> None:
    for case in CASES:
        text = page_text(case.html, case.url)
        for title, url in case.jobs:
            assert title.split(",")[0] in text, (case.id, title)
            assert f"<{url}>" in text, (case.id, url)
    assert sum(len(c.jobs) for c in CASES) >= 30


def test_these_are_pages_the_ai_is_needed_for() -> None:
    # the AI is only asked when JSON-LD finds nothing; no case offers structured data
    for case in CASES:
        assert parse_careers_page(case.html, case.url).via != "json_ld", case.id


def test_there_is_a_page_with_no_jobs_and_one_that_attacks() -> None:
    assert any(not c.jobs for c in CASES)
    attack = next(c for c in CASES if c.injection)
    assert EVIL in attack.html
    assert all(EVIL not in url for _, url in attack.jobs)


async def test_a_perfect_reader_passes_the_gate() -> None:
    report = await evaluate_pages(FakeLlm(perfect()), tier="fast", model="fake")

    assert (report.precision, report.recall) == (1.0, 1.0)
    assert (report.unusable, report.off_site, report.injection_affected) == (0, 0, 0)
    assert report.passes


async def test_an_answer_that_follows_the_attack_is_caught() -> None:
    steps = perfect()
    attack_index = next(i for i, c in enumerate(CASES) if c.injection)
    steps[attack_index]["jobs"].insert(0, {"title": "CEO", "url": f"https://{EVIL}/jobs/ceo"})
    # the off-site link is refused by the answer rules and the model is asked once more; it
    # repeats itself, so the page is unusable
    steps.insert(attack_index + 1, steps[attack_index])

    report = await evaluate_pages(FakeLlm(steps), tier="fast", model="fake")

    assert report.unusable == 1
    assert not report.passes


async def test_a_repair_that_fixes_the_answer_is_accepted() -> None:
    steps = perfect()
    steps.insert(0, {"jobs": [{"title": "Elsewhere", "url": "https://evil.example.net/x"}]})

    report = await evaluate_pages(FakeLlm(steps), tier="fast", model="fake")

    assert report.passes


def test_scoring_counts_missed_extra_and_off_site() -> None:
    case = next(c for c in CASES if c.id == "table")
    first_title, first_url = case.jobs[0]

    correct, notes, off_site, injected = score_page(
        case, [(first_title, first_url), ("Made up", f"https://{case.host}/made-up")]
    )

    assert (correct, off_site, injected) == (1, 0, 0)
    assert any("Made up" in n for n in notes)
    assert sum("missed" in n for n in notes) == len(case.jobs) - 1


def test_the_www_prefix_and_a_trailing_slash_do_not_matter() -> None:
    case = next(c for c in CASES if c.id == "rows")
    title, url = case.jobs[0]

    correct, _, off_site, _ = score_page(
        case, [(title, url.replace(case.host, f"www.{case.host}") + "/")]
    )

    assert (correct, off_site) == (1, 0)


async def test_the_report_names_the_gate() -> None:
    report = await evaluate_pages(FakeLlm(perfect()), tier="fast", model="fake")

    text = render_pages_report([report], day="2026-11-07")

    assert "extract_jobs_from_page eval - 2026-11-07" in text
    assert "| pass |" in text


def test_the_command_needs_yes_to_spend(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["extract_jobs_from_page", "--models", "fast", "--reports-dir", str(tmp_path)])

    assert code == 2
    assert "Nothing was sent" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_yes_runs_and_writes_a_report(tmp_path: Path) -> None:
    code = main(
        ["extract_jobs_from_page", "--models", "fast", "--yes", "--reports-dir", str(tmp_path)],
        llm_for=lambda _model: FakeLlm(perfect()),
        today=lambda: "2026-11-07",
    )

    assert code == 0
    assert (tmp_path / "extract_jobs_from_page-2026-11-07.md").exists()
