"""T027: the relevance eval set and runner. Uses FakeLlm: no network."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from evals.judge_relevance.cases import POSTINGS, PROFILES, Posting
from evals.judge_relevance.cases_go import GO_POSTINGS, LEFT_OUT_KINDS, postings_for
from evals.judge_relevance.runner import (
    BATCH,
    JudgeReport,
    evaluate_judge,
    render_judge_report,
)

from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import AiUnavailable


def label(profile: str, posting: Posting) -> bool:
    if profile == "backend_go":
        assert posting.go is not None
        return posting.go
    return posting.backend if profile == "backend" else posting.frontend


DECISIONS = 2 * len(POSTINGS) + len(GO_POSTINGS)  # two profiles on 60, one on the Go set


def script(decide: Callable[[str, Posting], bool]) -> list[dict[str, Any]]:
    """One scripted answer per call, in the order the runner makes them."""
    steps: list[dict[str, Any]] = []
    for profile in PROFILES:
        postings = postings_for(profile)
        for start in range(0, len(postings), BATCH):
            chunk = postings[start : start + BATCH]
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
    assert set(PROFILES) == {"backend", "frontend", "backend_go"}
    assert all(isinstance(p.backend, bool) and isinstance(p.frontend, bool) for p in POSTINGS)
    kinds = {p.kind for p in POSTINGS}
    assert {"match", "near_miss", "unrelated", "injection", "missing_facts", "seniority"} <= kinds
    assert sum(label("backend", p) for p in POSTINGS) >= 15
    assert sum(label("frontend", p) for p in POSTINGS) >= 15
    assert sum(not label("backend", p) for p in POSTINGS) >= 15


def test_injection_cases_present() -> None:
    attacks = [p for p in POSTINGS if p.injection]
    assert len(attacks) == 6
    profiles = ("backend", "frontend")
    assert any(label(profile, p) for p in attacks for profile in profiles)  # some stay relevant
    assert any(not label(profile, p) for p in attacks for profile in profiles)


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
    assert perfect.decisions == DECISIONS

    # always "relevant": recall stays 1, precision falls to the share of true labels
    greedy = run(script(lambda _p, _posting: True))
    trues = sum(label(pr, p) for pr in PROFILES for p in postings_for(pr))
    assert greedy.recall == 1.0
    assert greedy.precision == pytest.approx(trues / DECISIONS)
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

    assert report.decisions == 2 * DECISIONS
    # p01 differs for the two profiles that judge it
    assert report.consistency == pytest.approx((DECISIONS - 2) / DECISIONS)


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


# --- 002i: the Python and Go back end profile and SC-008 -------------------------------------


def test_FR035_the_go_profile_and_its_postings() -> None:
    card = PROFILES["backend_go"]
    assert (card.areas, card.years_experience) == (("back_end",), 4.5)  # type: ignore[comparison-overlap]
    assert card.recent_titles
    assert "Go" in card.key_skills
    assert len(GO_POSTINGS) >= 40
    assert len({p.id for p in GO_POSTINGS}) == len(GO_POSTINGS)
    assert all(isinstance(p.go, bool) for p in GO_POSTINGS)
    kinds = {p.kind for p in GO_POSTINGS}
    assert kinds >= {
        "match",
        "generic_relevant",
        "generic_irrelevant",
        "other_area",
        "other_stack",
        "no_description",
        "no_description_other",
        "above_level",
        "injection",
    }


def test_FR035_the_go_postings_cover_each_situation_of_the_spec() -> None:
    titles = {p.title for p in GO_POSTINGS}
    assert "Senior Software Engineer - BackEnd ( Java )" in titles  # Ravi's Java role
    assert "Senior Software Engineer - Frontend" in titles  # and his front end role
    blank = [p for p in GO_POSTINGS if not p.description.strip()]
    assert len(blank) >= 5  # postings whose own text could not be read
    assert any(p.go for p in blank)  # a generic title without text is kept
    assert any(not p.go for p in blank)  # a title naming another area is not
    assert all(not p.go for p in GO_POSTINGS if p.kind in LEFT_OUT_KINDS)
    assert (
        sum(p.kind in LEFT_OUT_KINDS for p in GO_POSTINGS) >= 16
    )  # enough that 1 miss in 3 runs passes
    assert sum(bool(p.go) for p in GO_POSTINGS) >= 15


def test_FR035_the_go_set_is_invented() -> None:
    text = " ".join(f"{p.company} {p.title} {p.description}" for p in GO_POSTINGS).lower()
    assert "example" in text
    assert "@" not in text


def test_FR035_the_go_postings_are_not_judged_for_the_other_profiles() -> None:
    assert postings_for("backend") is POSTINGS
    assert postings_for("frontend") is POSTINGS
    assert postings_for("backend_go") is GO_POSTINGS


def test_SC008_a_perfect_run_leaves_out_and_keeps_everything_right() -> None:
    report = run(script(label))
    assert (report.left_out_ok, report.left_out_total) == (
        sum(p.kind in LEFT_OUT_KINDS for p in GO_POSTINGS),
        sum(p.kind in LEFT_OUT_KINDS for p in GO_POSTINGS),
    )
    assert (report.left_out_rate, report.go_recall) == (1.0, 1.0)
    assert report.passes


def test_SC008_keeping_every_job_fails_the_gate_on_left_out_roles() -> None:
    report = run(script(lambda _profile, _posting: True))
    assert report.left_out_rate == 0.0
    assert report.go_recall == 1.0
    assert not report.passes


def test_SC008_leaving_out_every_job_fails_the_gate_on_the_relevant_ones() -> None:
    report = run(script(lambda _profile, _posting: False))
    assert report.left_out_rate == 1.0
    assert report.go_recall == 0.0
    assert not report.passes


def test_SC008_one_miss_in_a_single_run_is_below_the_bar() -> None:
    missed = next(p.id for p in GO_POSTINGS if p.kind == "other_stack")

    def decide(profile: str, posting: Posting) -> bool:
        return True if posting.id == missed else label(profile, posting)

    report = run(script(decide))
    total = sum(p.kind in LEFT_OUT_KINDS for p in GO_POSTINGS)
    assert report.left_out_rate == pytest.approx((total - 1) / total)
    assert not report.passes  # a single run that misses one is under 95%


def test_SC008_the_report_shows_both_measures() -> None:
    text = render_judge_report([run(script(label))], day="2026-11-16")
    assert "left out (SC-008)" in text
    assert "Go profile recall" in text
    assert "100.0% (" in text


def test_a_candidate_prompt_version_is_loaded_from_its_own_folder(tmp_path: Path) -> None:
    """A new version is evaluated from a folder of candidates, before it is active."""
    import shutil

    from evals.judge_relevance import runner

    active = runner._registry()
    source = Path(runner.hiretitan_prompts.__file__).parent / "judge_relevance" / "v3"  # type: ignore[attr-defined]
    candidate = tmp_path / "judge_relevance" / "v9"
    shutil.copytree(source, candidate)
    (candidate / "meta.yaml").write_text(
        (source / "meta.yaml").read_text(encoding="utf-8").replace("version: 3", "version: 9"),
        encoding="utf-8",
    )

    loaded = runner._registry(tmp_path).load("judge_relevance", 9)

    assert loaded.version.version == 9
    assert active.load("judge_relevance").version.version == 3  # the active ones are untouched
    # and the checks that go with a candidate are its own
    assert runner._checks(tmp_path, 9).has_link("See acme.com")
