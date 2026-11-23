"""T066: the ``read_job_alert`` eval (SC-011) with a scripted AI; no key, no credit."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from evals.read_job_alert.runner import COMPANY_FILLED_MIN, JOB_RECALL_MIN, evaluate, load_emails
from evals.run import main

from hiretitan.mail.application.alert_prompt import shown_links
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import AiUnavailable


def perfect() -> list[dict[str, Any]]:
    """What a perfect AI answers, email by email, in the order the eval asks."""
    answers = []
    for email in load_emails():
        index = {link.href: n for n, link in enumerate(shown_links(email.flat), 1)}
        answers.append(
            {
                "jobs": [
                    {
                        "title": want["title"],
                        "company": want["company"],
                        "location": want.get("location"),
                        "link_index": index[want["link"]],
                    }
                    for want in email.expected
                    if want["link"] in index
                ]
            }
        )
    return answers


def test_SC011_the_set_holds_every_site_the_unknown_layouts_and_the_planted_emails() -> None:
    emails = load_emails()

    assert {e.site for e in emails} >= {"linkedin", "naukri", "indeed", "other"}
    assert sum(1 for e in emails if e.name.startswith("unknown-")) == 3
    assert sum(1 for e in emails if e.injection) >= 2
    assert all(e.expected for e in emails if e.name.startswith("unknown-"))


def test_SC011_a_perfect_ai_passes() -> None:
    report = asyncio.run(evaluate(FakeLlm(perfect()), tier="fast", model="fake"))

    assert report.ai_alone.recall >= JOB_RECALL_MIN
    assert report.ai_alone.company_rate >= COMPANY_FILLED_MIN
    assert (report.ai_alone.invented, report.ai_alone.footer, report.unusable) == (0, 0, 0)
    assert report.passes


def test_SC011_an_ai_that_finds_nothing_fails_even_though_the_fixed_readers_fill_in() -> None:
    nothing: list[dict[str, Any]] = [{"jobs": []}] * len(load_emails())

    report = asyncio.run(evaluate(FakeLlm(nothing), tier="fast", model="fake"))

    assert report.ai_alone.recall == 0
    assert report.ai_first.recall > 0.9  # the check would still store the fixed readers' jobs
    assert not report.passes


def test_SC011_footer_and_invented_values_never_reach_a_job() -> None:
    emails = load_emails()
    answers = perfect()
    for answer in answers:
        for job in answer["jobs"]:
            job["company"] = "This email was intended for Jane"  # dropped: not a value
            job["location"] = "Atlantis"  # dropped: not in the email

    report = asyncio.run(evaluate(FakeLlm(answers), tier="fast", model="fake", emails=emails))

    assert (report.ai_alone.invented, report.ai_alone.footer) == (0, 0)
    assert report.ai_alone.company_rate < COMPANY_FILLED_MIN
    assert not report.passes


def test_SC011_the_command_needs_yes_to_spend(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["read_job_alert", "--models", "fast", "--reports-dir", str(tmp_path)])

    assert code == 2
    assert "Nothing was sent" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_SC011_yes_runs_and_writes_a_report(tmp_path: Path) -> None:
    code = main(
        ["read_job_alert", "--models", "fast", "--yes", "--reports-dir", str(tmp_path)],
        llm_for=lambda _model: FakeLlm(perfect()),
        today=lambda: "2026-11-24",
    )

    assert code == 0
    report = (tmp_path / "read_job_alert-2026-11-24.md").read_text("utf-8")
    assert "| pass |" in report


def test_SC011_an_unavailable_ai_writes_no_report(tmp_path: Path) -> None:
    code = main(
        ["read_job_alert", "--models", "fast", "--yes", "--reports-dir", str(tmp_path)],
        llm_for=lambda _model: FakeLlm([AiUnavailable("key_rejected")]),
    )

    assert code == 1
    assert list(tmp_path.iterdir()) == []
