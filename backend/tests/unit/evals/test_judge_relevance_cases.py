"""T027: the relevance eval set and runner. Uses FakeLlm: no network, no cost."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from evals.judge_relevance.cases import POSTINGS, PROFILES, Posting
from evals.judge_relevance.runner import (
    BATCH,
    JudgeReport,
    evaluate_judge,
    render_judge_report,
)

from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import AiUnavailable


def label(profile: str, posting: Posting) -> bool:
    return posting.backend if profile == "backend" else posting.frontend


def script(decide: Callable[[str, Posting], bool]) -> list[dict[str, Any]]:
    """One scripted answer per call, in the order the runner makes them."""
    steps: list[dict[str, Any]] = []
    for profile in PROFILES:
        for start in range(0, len(POSTINGS), BATCH):
            chunk = POSTINGS[start : start + BATCH]
            steps.append(
                {
                    "decisions": [
                        {"ref": f"j{i}", "relevant": decide(profile, p), "reason": "Scripted."}
                        for i, p in enumerate(chunk, start=1)
                    ]
                }
            )
    return steps


def run(steps: list[dict[str, Any]], repeat: int = 1) -> JudgeReport:
    llm = FakeLlm(by_task={"judge_relevance": steps * repeat})
    return asyncio.run(evaluate_judge(llm, tier="fast", model="fake-model", repeat=repeat))


def test_60_postings_two_profiles_all_labelled() -> None:
    assert len(POSTINGS) == 60
    assert len({p.id for p in POSTINGS}) == 60
    assert set(PROFILES) == {"backend", "frontend"}
    assert all(isinstance(p.backend, bool) and isinstance(p.frontend, bool) for p in POSTINGS)
    kinds = {p.kind for p in POSTINGS}
    assert {"match", "near_miss", "unrelated", "injection", "missing_facts", "seniority"} <= kinds
    assert sum(label("backend", p) for p in POSTINGS) >= 15
    assert sum(label("frontend", p) for p in POSTINGS) >= 15
    assert sum(not label("backend", p) for p in POSTINGS) >= 15


def test_injection_cases_present() -> None:
    attacks = [p for p in POSTINGS if p.injection]
    assert len(attacks) == 6
    assert any(label(profile, p) for p in attacks for profile in PROFILES)  # some stay relevant
    assert any(not label(profile, p) for p in attacks for profile in PROFILES)


def test_postings_missing_a_place_or_date_are_present() -> None:
    missing = [p for p in POSTINGS if p.location is None]
    assert len(missing) >= 5
    assert all(label("backend", p) or label("frontend", p) for p in missing)


def test_names_and_places_are_invented() -> None:
    text = " ".join(f"{p.company} {p.title} {p.description}" for p in POSTINGS).lower()
    assert "example" in text
    assert "@" not in text  # no emails


def test_runner_scores_precision_recall() -> None:
    perfect = run(script(label))
    assert (perfect.precision, perfect.recall) == (1.0, 1.0)
    assert (perfect.unusable, perfect.injection_affected, perfect.consistency) == (0, 0, 1.0)
    assert perfect.decisions == 120

    # always "relevant": recall stays 1, precision falls to the share of true labels
    greedy = run(script(lambda _p, _posting: True))
    trues = sum(label(pr, p) for pr in PROFILES for p in POSTINGS)
    assert greedy.recall == 1.0
    assert greedy.precision == pytest.approx(trues / 120)
    assert greedy.injection_affected > 0  # it said yes to injected, irrelevant jobs

    # always "not relevant": precision is vacuously 1, recall is 0
    stingy = run(script(lambda _p, _posting: False))
    assert (stingy.precision, stingy.recall) == (1.0, 0.0)


def test_unusable_answers_are_counted_and_hurt_recall() -> None:
    steps = script(label)
    steps[0] = {"decisions": []}  # misses every ref: repaired once, then falls back
    llm = FakeLlm(by_task={"judge_relevance": [steps[0], steps[0], *steps[1:]]})

    report = asyncio.run(evaluate_judge(llm, tier="fast", model="fake-model"))

    assert report.unusable == BATCH
    assert report.recall < 1.0
    assert report.precision == 1.0


def test_repeat_measures_consistency() -> None:
    steps = script(label)
    flipped = script(
        lambda profile, p: (not label(profile, p)) if p.id == "p01" else label(profile, p)
    )
    llm = FakeLlm(by_task={"judge_relevance": [*steps, *flipped]})

    report = asyncio.run(evaluate_judge(llm, tier="fast", model="fake-model", repeat=2))

    assert report.decisions == 240
    assert report.consistency == pytest.approx(118 / 120)  # p01 differs for both profiles


def test_no_key_stops_the_whole_eval() -> None:
    llm = FakeLlm(by_task={"judge_relevance": [AiUnavailable("key_missing")]})
    with pytest.raises(AiUnavailable):
        asyncio.run(evaluate_judge(llm, tier="fast", model="fake-model"))


def test_report_shows_the_gates() -> None:
    text = render_judge_report([run(script(label))], day="2026-11-06")
    assert "judge_relevance eval - 2026-11-06" in text
    assert "precision" in text.lower()
    assert "pass" in text
    bad = render_judge_report([run(script(lambda _p, _q: True))], day="2026-11-06")
    assert "FAIL" in bad
