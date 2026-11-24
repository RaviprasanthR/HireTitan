"""The outreach and tailor evals (T019, T027): SC-004, SC-005. No network: a scripted model."""

from __future__ import annotations

import re
from typing import Any

import pytest
from evals.drafts.cases import PROFILES, SEEDED_FABRICATIONS, build_cases
from evals.drafts.runner import (
    DraftReport,
    evaluate_outreach,
    evaluate_tailor,
    render_report,
    seeded_detection,
)
from evals.run import main

from hiretitan.drafts_wiring import tech_terms
from hiretitan.platform.llm.port import LlmRequest, LlmResult, Usage
from hiretitan.search.domain.tech_names import TechName


class AnyAnswerLlm:
    """Answers every request with a plain valid result, as a well-behaved model would."""

    provider = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[LlmRequest[Any]] = []

    async def generate[T: Any](self, req: LlmRequest[T]) -> LlmResult[T]:
        self.calls.append(req)
        answers: dict[str, dict[str, Any]] = {
            "extract_job_keywords": {
                "role_summary": "Engineer.",
                "keywords": ["Python", "APIs"],
                "must_have": ["Python"],
            },
            "draft_connection_request": {
                "body": "Hi {recipient_first_name}, I am interested in this role and would be glad "
                "to connect.",
                "cited_fact_ids": [],
            },
            "draft_referral_message": {
                "greeting": "Hi {recipient_first_name},",
                "body": "I saw this role and would value your advice on the team.",
                "easy_out": "No pressure at all, and I completely understand if it's not possible.",
                "sign_off": "Thanks, {my_name}",
                "cited_fact_ids": [],
            },
            "draft_email": {
                "subject": "About the role",
                "greeting": "Hi {recipient_first_name},",
                "body": "I saw this role and would be glad to share more about my work.",
                "closing": "Thank you for your time, and no worries if now is not a good moment.",
                "cited_fact_ids": [],
            },
            "tailor_resume": {
                "summary": "Engineer who builds reliable software.",
                "experience": [],
                "skills": [],
                "project_ids": [],
            },
        }
        value = req.output_schema.model_validate(answers[req.task])
        return LlmResult(value, "ok", Usage(10, 0, 20, 120), self.provider, self.model)


def test_SC004_cases_are_synthetic() -> None:
    cases = build_cases()
    assert len(cases) == 30
    assert {c.recipient_kind for c in cases} == {"recruiter", "hiring_manager", "engineer", "other"}
    assert any(c.language == "de" for c in cases)
    assert any(c.injected for c in cases)
    assert max(len(c.description) for c in cases) > 5000  # a long posting
    for profile in PROFILES:
        email = profile.contact.email or ""
        assert email.endswith("@example.invalid"), "a synthetic address only"
        assert profile.contact.phone is None
        assert not re.search(r"https?://", repr(profile))
    # nobody real: the maintainer's own details are never copied into the repo
    names = {p.contact.name for p in PROFILES}
    assert names == {
        "Aria Voss",
        "Bruno Keller",
        "Chloe Mbeki",
        "Dmitri Okafor",
        "Elena Park",
        "Farid Lindqvist",
    }


def test_SC004_scorer_counts_seeded_fabrications() -> None:
    terms = tech_terms(
        (
            TechName("Python", "language", ()),
            TechName("Java", "language", ()),
            TechName("Kubernetes", "framework", ("k8s",)),
            TechName("Rust", "language", ()),
        )
    )

    caught, total = seeded_detection(terms)

    assert total == len(SEEDED_FABRICATIONS) == 20
    assert caught == total


async def test_SC005_outreach_report_has_tier_columns_and_passes() -> None:
    llm = AnyAnswerLlm()
    fast = await evaluate_outreach(llm, tier="fast", model="m-fast", cases=build_cases()[:6])
    strong = await evaluate_outreach(llm, tier="strong", model="m-strong", cases=build_cases()[:6])

    assert fast.drafts == 18  # three kinds: connection request, LinkedIn message, email
    assert fast.first_try_ok == 18
    assert fast.fabrications == 0
    assert fast.length_ok == fast.length_total == 6
    assert fast.referral_first_try_rate == 1.0
    assert fast.p95_ms == 120
    text = render_report([fast, strong], day="2026-11-17")
    header = text.splitlines()[4]
    assert "fast (m-fast)" in header
    assert "strong (m-strong)" in header
    assert "p95 latency ms" in text
    assert "Referral tone accepted first try" in text
    assert fast.passes


async def test_SC006_tailor_report_has_keyword_scores() -> None:
    report = await evaluate_tailor(
        AnyAnswerLlm(), tier="strong", model="m", cases=build_cases()[:4]
    )

    assert report.task == "tailor_resume"
    assert report.drafts == 4
    assert len(report.keyword_before) == len(report.keyword_after) == 4
    assert "Keyword match after" in render_report([report], day="2026-11-17")


def test_SC005_a_report_with_a_fabrication_does_not_pass() -> None:
    bad = DraftReport("outreach_drafts", "m", "fast", 1, seeded_total=20, seeded_caught=20)
    assert bad.passes
    bad.fabrications = 1
    assert not bad.passes
    slow = DraftReport("tailor_resume", "m", "strong", 1, seeded_total=20, seeded_caught=20)
    slow.latencies = [70_000]
    assert not slow.passes  # over the 60 s goal


@pytest.mark.parametrize("eval_name", ["outreach_drafts", "tailor_resume"])
def test_the_runner_does_nothing_without_yes(eval_name: str, tmp_path: Any) -> None:
    assert main([eval_name, "--models", "fast,strong", "--reports-dir", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == []
