"""T051: the extraction eval runner (SC-003). Uses FakeLlm: no network, no cost."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from evals import run as eval_run
from evals.extract_profile.cases import CASES_DIR, EXPECTED_DIR, MID_DATES, SENIOR_DATES
from evals.run import CaseScore, evaluate, load_cases, score_case

from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import LlmPort
from hiretitan.profile.infra.parsing.docx import parse_docx
from hiretitan.profile.infra.parsing.pdf import parse_pdf


def extracted(expected: dict[str, Any]) -> dict[str, Any]:
    """An ``ExtractedProfile`` JSON that says exactly what the expected facts say."""
    experience = [
        {
            "employer": employer,
            "title": title,
            "location": None,
            "start": None,
            "end": None,
            "current": False,
            "bullets": [],
        }
        for employer, title in zip(expected["employers"], expected["titles"], strict=True)
    ]
    return {
        "contact": {"name": expected["name"], "location": None},
        "headline": None,
        "summary": None,
        "experience": experience,
        "education": [
            {
                "institution": name,
                "qualification": None,
                "field": None,
                "start": None,
                "end": None,
                "grade": None,
            }
            for name in expected["education"]
        ],
        "skills": list(expected["skills"]),
        "projects": [],
        "certifications": [],
    }


def with_dates(payload: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """Put each job's known start and end (``YYYY-MM``) on the experience entries."""
    known = {**MID_DATES, **SENIOR_DATES}
    if expected["dates"] == ["2020-01"]:  # the Spanish resume
        known["Acme Corp"] = ("2020-01", None)
    for item in payload["experience"]:
        for key, value in zip(("start", "end"), known[item["employer"]], strict=True):
            if value:
                year, month = value.split("-")
                item[key] = {"year": int(year), "month": int(month)}
    return payload


def perfect_script() -> list[dict[str, Any]]:
    out = []
    for case in load_cases(CASES_DIR, EXPECTED_DIR):
        out.append(extracted(case.expected))
    return out


def test_twelve_cases_cover_the_required_shapes() -> None:
    cases = load_cases(CASES_DIR, EXPECTED_DIR)
    names = {c.path.name for c in cases}

    assert len(cases) == 12
    assert {p.suffix for p in map(Path, names)} == {".pdf", ".docx"}
    assert any("two-column" in n for n in names)
    assert any("fresher" in n for n in names)
    assert any("senior" in n for n in names)
    assert any("non-english" in n for n in names)
    assert any("tables" in n for n in names)
    assert any("textboxes" in n for n in names)


def test_expected_facts_are_present_in_the_parsed_text() -> None:
    """The ground truth must be findable in the file, or the eval would blame the model."""
    for case in load_cases(CASES_DIR, EXPECTED_DIR):
        data = case.path.read_bytes()
        text = (parse_pdf(data) if case.path.suffix == ".pdf" else parse_docx(data)).visible_text
        folded = text.casefold()
        for key in ("employers", "titles", "skills", "education"):
            for fact in case.expected[key]:
                assert fact.casefold() in folded, f"{case.path.name}: {key} {fact!r} missing"


def test_SC003_precision_recall_computed() -> None:
    cases = load_cases(CASES_DIR, EXPECTED_DIR)
    script = perfect_script()
    # Make one case wrong: lose a job, and add a skill that is in the text (so grounding keeps it)
    # but is not one of the person's skills (an employer name).
    first = next(i for i, c in enumerate(cases) if c.expected["employers"])
    script[first]["experience"].pop()
    script[first]["skills"].append(cases[first].expected["employers"][0])
    llm = FakeLlm(by_task={"extract_profile": script})

    report = asyncio.run(evaluate(llm, cases, tier="fast", model="fake-model"))

    total_employers = sum(len(c.expected["employers"]) for c in cases)
    total_skills = sum(len(c.expected["skills"]) for c in cases)
    employers = report.fields["employers"]
    skills = report.fields["skills"]
    assert employers.recall == pytest.approx((total_employers - 1) / total_employers)
    assert employers.precision == pytest.approx(1.0)
    assert skills.precision == pytest.approx(total_skills / (total_skills + 1))
    assert skills.recall == pytest.approx(1.0)
    assert report.fields["titles"].recall < 1.0  # the lost job took its title with it
    assert len(report.cases) == 12


def test_score_case_normalises_case_and_whitespace() -> None:
    expected = {
        "employers": ["Acme Corp"],
        "titles": [],
        "dates": [],
        "skills": [],
        "education": [],
    }
    got = {
        "employers": ["  acme   corp "],
        "titles": [],
        "dates": [],
        "skills": [],
        "education": [],
    }

    score = score_case(expected, got)

    assert score.counts["employers"] == (1, 1, 1)  # hits, extracted, expected
    assert isinstance(score, CaseScore)


def test_dates_are_compared_as_year_month() -> None:
    # Not the Spanish resume: grounding does not know "ene" as a month, so it drops that date's
    # month. That is a real finding for the eval report (see the T051 notes), not a runner bug.
    cases = [c for c in load_cases(CASES_DIR, EXPECTED_DIR) if c.path.name != "non-english.pdf"]
    script = [with_dates(extracted(c.expected), c.expected) for c in cases]
    llm = FakeLlm(by_task={"extract_profile": script})

    report = asyncio.run(evaluate(llm, cases, tier="fast", model="fake-model"))

    assert report.fields["dates"].recall == pytest.approx(1.0)
    assert report.fields["dates"].precision == pytest.approx(1.0)


def test_unusable_answers_count_as_empty_not_as_a_crash() -> None:
    cases = [c for c in load_cases(CASES_DIR, EXPECTED_DIR) if c.expected["employers"]][:2]
    llm = FakeLlm(by_task={"extract_profile": [{"nonsense": True}] * 4})

    report = asyncio.run(evaluate(llm, cases, tier="fast", model="fake-model"))

    assert report.fields["employers"].recall == 0.0
    assert report.failed_cases == 2


def run_main(argv: list[str], llm: FakeLlm, tmp_path: Path) -> int:
    def build(model: str) -> LlmPort:
        return llm

    return eval_run.main(
        [*argv, "--reports-dir", str(tmp_path)], llm_for=build, today=lambda: "2026-11-04"
    )


def test_estimate_printed_and_confirmation_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = FakeLlm(by_task={"extract_profile": perfect_script()})

    code = run_main(["extract_profile", "--models", "fast,strong"], llm, tmp_path)

    out = capsys.readouterr().out
    assert code != 0
    assert "Estimated cost" in out
    assert "--yes" in out
    assert llm.calls == []  # nothing was sent
    assert list(tmp_path.iterdir()) == []  # and no report written


def test_yes_runs_and_writes_a_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    llm = FakeLlm(by_task={"extract_profile": perfect_script()})

    code = run_main(["extract_profile", "--models", "fast", "--yes"], llm, tmp_path)

    report = tmp_path / "extract_profile-2026-11-04.md"
    assert code == 0
    assert len(llm.calls) == 12
    text = report.read_text("utf-8")
    assert "| fast" in text
    assert "precision" in text.lower()
    assert "p95" in text.lower()
    assert "employers" in text
    assert "skills" in text
    assert capsys.readouterr().out.count("Estimated cost") == 1


def test_estimate_uses_catalog_prices() -> None:
    cases = load_cases(CASES_DIR, EXPECTED_DIR)

    cheap = eval_run.estimate_cost(cases, "gpt-5.4-mini")
    dear = eval_run.estimate_cost(cases, "gpt-6-astra")

    assert Decimal(0) < cheap < dear


def test_unknown_model_is_rejected_with_a_clear_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = FakeLlm()

    code = run_main(["extract_profile", "--models", "nano", "--yes"], llm, tmp_path)

    assert code != 0
    assert "nano" in capsys.readouterr().out


def test_expected_files_are_valid_yaml_with_all_fields() -> None:
    for path in EXPECTED_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text("utf-8"))
        assert set(data) >= {"name", "employers", "titles", "dates", "skills", "education"}


def test_provider_error_on_one_case_does_not_abort_the_run() -> None:
    cases = [c for c in load_cases(CASES_DIR, EXPECTED_DIR) if c.expected["employers"]][:2]
    good = extracted(cases[1].expected)
    llm = FakeLlm(by_task={"extract_profile": [RuntimeError("429 rate limited"), good]})

    report = asyncio.run(evaluate(llm, cases, tier="fast", model="fake-model"))

    assert [c.outcome for c in report.cases] == ["error", "ok"]
    assert report.failed_cases == 1
