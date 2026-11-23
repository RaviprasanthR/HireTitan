"""T046: the alert-reader eval (SC-002, readers part; no AI)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from evals.mail_alerts.runner import (
    JOB_RECALL_MIN,
    READ_WITHOUT_AI_MIN,
    evaluate,
    render_report,
    score_email,
)
from evals.run import main

from hiretitan.mail.domain.alerts import AlertJob

WHEN = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


def job(title: str, company: str | None, link: str, location: str | None = None) -> AlertJob:
    return AlertJob(title, company, location, link, None, "linkedin", WHEN)


def expected(title: str, company: str | None, link: str) -> dict[str, str | None]:
    return {"title": title, "company": company, "location": None, "link": link}


def test_SC002_a_job_counts_only_with_title_company_and_link_right() -> None:
    wanted = [
        expected("Data Engineer", "Acme", "https://x.example/1"),
        expected("QA Engineer", "Beta", "https://x.example/2"),
        expected("SRE", None, "https://x.example/3"),
    ]
    found = [
        job("Data Engineer", "Acme", "https://x.example/1"),
        job("QA Engineer", "Gamma", "https://x.example/2"),  # wrong company
    ]

    score = score_email(wanted, found, "Data Engineer Acme QA Engineer Beta Gamma SRE")

    assert (score.expected, score.correct) == (3, 1)
    assert (score.titles, score.companies, score.links) == (2, 1, 2)
    assert score.invented == 0
    assert score.read_without_ai


def test_SC002_values_not_in_the_email_and_extra_jobs_are_invented() -> None:
    wanted = [expected("Data Engineer", "Acme", "https://x.example/1")]
    found = [
        job("Data Engineer", "Acme", "https://x.example/1", location="Mars"),  # not in the text
        job("Made Up Role", "Acme", "https://x.example/9"),  # a job the email does not hold
    ]

    score = score_email(wanted, found, "Data Engineer Acme")

    assert score.invented == 3  # "Mars", "Made Up Role", and the job itself
    assert score.correct == 1


def test_SC002_an_email_the_reader_cannot_read_is_left_to_the_ai() -> None:
    score = score_email([expected("SRE", "Acme", "https://x.example/1")], [], "SRE Acme")

    assert not score.read_without_ai
    assert score.correct == 0


def test_SC002_fixtures_cover_every_site_and_meet_the_targets() -> None:
    report = evaluate()

    sites = {s.site: s for s in report.sites}
    assert set(sites) == {"linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort"}
    assert all(s.emails >= 10 for s in sites.values())
    assert report.emails >= 60
    assert report.job_recall >= JOB_RECALL_MIN
    assert report.invented == 0
    assert report.read_without_ai >= READ_WITHOUT_AI_MIN
    assert report.unknown_layouts == 3  # the three digests no fixed reader knows go to the AI
    assert report.passes


def test_SC002_report_names_targets_and_holds_no_job_values() -> None:
    text = render_report(evaluate(), day="2026-11-23")

    for needed in ("mail_alerts", "PASS", "95%", "90%", "linkedin"):
        assert needed in text
    assert "https://" not in text  # counts only, no links or titles


def test_SC002_runner_task_writes_a_report_without_ai(tmp_path: Path) -> None:
    code = main(["mail_alerts", "--reports-dir", str(tmp_path)], today=lambda: "2026-11-23")

    assert code == 0
    assert (tmp_path / "mail_alerts-2026-11-23.md").exists()
