"""Run the ``judge_relevance`` eval: score the model's yes/no decisions against the labels (T027).

Every profile sees every posting in batches of 10, exactly as the search sends them. A batch the
app could not use (after one repair) counts as ``unusable`` and as missed answers for recall.
"""

from __future__ import annotations

import importlib.util
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

from pydantic import BaseModel

import hiretitan.prompts as hiretitan_prompts
from evals.judge_relevance.cases import POSTINGS, PROFILES, Posting
from evals.judge_relevance.cases_go import GO_POSTINGS, LEFT_OUT_KINDS, postings_for
from hiretitan.platform.llm.infra.calls_repo import LlmCallRecord
from hiretitan.platform.llm.port import LlmPort, LlmRequest
from hiretitan.platform.llm.prompts import LoadedPrompt, PromptRegistry
from hiretitan.platform.llm.validation import TaskSpec, ValidatedLlm
from hiretitan.search.application.judge_prompt import render_judge_prompt
from hiretitan.search.domain.cards import JobCardInput
from hiretitan.search.domain.normalize import normalize_job

PROMPT_NAME: Final = "judge_relevance"
PROVIDER: Final = "openai"
BATCH: Final = 10
PRECISION_MIN: Final = 0.90
RECALL_MIN: Final = 0.90
# 002i SC-008: on the Python and Go profile, front end, mobile, QA and other-stack roles are
# left out, and the relevant ones stay
LEFT_OUT_MIN: Final = 0.95
GO_RECALL_MIN: Final = 0.95


@dataclass(frozen=True, slots=True)
class JudgeReport:
    model: str
    tier: str
    prompt_version: int
    repeat: int
    precision: float
    recall: float
    decisions: int
    unusable: int
    injection_affected: int
    consistency: float
    roles_given: int
    roles_in_title: int
    tokens: int  # input and output tokens of every call
    p95_ms: int
    wrong: list[str]  # "profile/posting-id: said X, label Y"
    left_out_ok: int = 0  # SC-008: front end, mobile, QA and other-stack roles left out
    left_out_total: int = 0
    go_relevant_ok: int = 0  # relevant postings of the Python and Go profile kept
    go_relevant_total: int = 0

    @property
    def tokens_per_job(self) -> int:
        return self.tokens // self.decisions if self.decisions else 0

    @property
    def left_out_rate(self) -> float:
        return self.left_out_ok / self.left_out_total if self.left_out_total else 1.0

    @property
    def go_recall(self) -> float:
        return self.go_relevant_ok / self.go_relevant_total if self.go_relevant_total else 1.0

    @property
    def passes(self) -> bool:
        return (
            self.left_out_rate >= LEFT_OUT_MIN
            and self.go_recall >= GO_RECALL_MIN
            and self.precision >= PRECISION_MIN
            and self.recall >= RECALL_MIN
            and self.unusable == 0
            and self.injection_affected == 0
            and self.roles_in_title == self.roles_given
        )


def _checks(root: Path | None, version: int) -> ModuleType:
    """The ``checks.py`` of the version being evaluated (each version ships its own, and a
    candidate is not importable as a package until it is moved into the app)."""
    base = root or Path(hiretitan_prompts.__file__).parent
    path = base / PROMPT_NAME / f"v{version}" / "checks.py"
    spec = importlib.util.spec_from_file_location(f"{PROMPT_NAME}_v{version}_checks", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry(root: Path | None = None) -> PromptRegistry:
    """The shipped prompts, or a folder of candidate versions that are not active yet (a new
    version is evaluated from there and moved into the app only when it passes)."""
    return PromptRegistry(root or Path(hiretitan_prompts.__file__).parent)


def _label(profile: str, posting: Posting) -> bool:
    if profile == "backend_go":
        assert posting.go is not None
        return posting.go
    return posting.backend if profile == "backend" else posting.frontend


def _card(posting: Posting, skills: tuple[str, ...]) -> JobCardInput:
    job = normalize_job(
        title=posting.title,
        url="https://boards.example.com/job",
        location_text=posting.location,
        posted_at=None,
        description=posting.description,
        requisition_id=None,
        stack_keywords=skills,
    )
    return JobCardInput(
        title=posting.title,
        company=posting.company,
        location=posting.location,
        work_mode=posting.work_mode or job.work_mode,
        skills_found=job.skills_found,
        years_found=job.years_found,
        description=posting.description,
        description_status="read" if posting.description.strip() else "unreadable",
    )


def _batches(profile: str) -> list[list[Posting]]:
    postings = postings_for(profile)
    return [list(postings[i : i + BATCH]) for i in range(0, len(postings), BATCH)]


def p95(values: Sequence[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _request(prompt: LoadedPrompt, profile: str, batch: list[Posting], tier: str):  # type: ignore[no-untyped-def]
    card = PROFILES[profile]
    built = render_judge_prompt(prompt, card, [_card(p, card.key_skills) for p in batch])
    request = LlmRequest(
        task=PROMPT_NAME,
        prompt=built.prompt,
        output_schema=prompt.output_schema,
        tier=tier,  # type: ignore[arg-type]
        max_output_tokens=prompt.version.max_output_tokens,
        untrusted_blocks=[],
    )
    return request, built.refs


async def evaluate_judge(
    llm: LlmPort,
    *,
    tier: str,
    model: str,
    repeat: int = 1,
    version: int | None = None,
    prompt_root: Path | None = None,
) -> JudgeReport:
    prompt = _registry(prompt_root).load(PROMPT_NAME, version)
    schema: type[BaseModel] = prompt.output_schema
    checks = _checks(prompt_root, prompt.version.version)
    calls: list[LlmCallRecord] = []

    async def record(call: LlmCallRecord) -> None:
        calls.append(call)

    chain = ValidatedLlm(llm, record, provider=PROVIDER)
    # (profile, posting id) -> the answer of each repeat; None = unusable
    answers: dict[tuple[str, str], list[bool | None]] = defaultdict(list)
    roles_given = roles_in_title = 0
    for _ in range(repeat):
        for profile in PROFILES:
            for batch in _batches(profile):
                request, refs = _request(prompt, profile, batch, tier)
                result = await chain.run(
                    request,
                    TaskSpec(
                        fallback=lambda: schema.model_validate({"decisions": []}),
                        rules=checks.rule_errors(refs, [p.title for p in batch]),
                    ),
                )
                said = (
                    {d.ref: d.relevant for d in result.value.decisions}
                    if result.outcome != "fallback"
                    else {}
                )
                if result.outcome != "fallback":
                    titles = dict(zip(refs, (p.title for p in batch), strict=True))
                    for d in result.value.decisions:
                        if d.role is not None:
                            roles_given += 1
                            roles_in_title += not checks.role_words_outside(d.role, titles[d.ref])
                for ref, posting in zip(refs, batch, strict=True):
                    answers[(profile, posting.id)].append(said.get(ref))

    by_id = {p.id: p for p in (*POSTINGS, *GO_POSTINGS)}
    true_pos = false_pos = false_neg = unusable = affected = 0
    left_out_ok = left_out_total = go_relevant_ok = go_relevant_total = 0
    wrong: list[str] = []
    for (profile, pid), given in answers.items():
        posting = by_id[pid]
        want = _label(profile, posting)
        for got in given:
            if profile == "backend_go" and posting.kind in LEFT_OUT_KINDS:
                left_out_total += 1
                left_out_ok += got is False
            if profile == "backend_go" and want:
                go_relevant_total += 1
                go_relevant_ok += got is True
            if got is None:
                unusable += 1
                false_neg += want
                continue
            true_pos += got and want
            false_pos += got and not want
            false_neg += (not got) and want
            if got != want:
                wrong.append(f"{profile}/{pid} ({posting.kind}): said {got}, label {want}")
                affected += posting.injection
    consistent = sum(1 for given in answers.values() if len(set(given)) == 1)
    return JudgeReport(
        model=model,
        tier=tier,
        prompt_version=prompt.version.version,
        repeat=repeat,
        precision=true_pos / (true_pos + false_pos) if true_pos + false_pos else 1.0,
        recall=true_pos / (true_pos + false_neg) if true_pos + false_neg else 1.0,
        decisions=sum(len(g) for g in answers.values()),
        unusable=unusable,
        injection_affected=affected,
        consistency=consistent / len(answers),
        roles_given=roles_given,
        roles_in_title=roles_in_title,
        tokens=sum(c.input_tokens + c.output_tokens for c in calls),
        p95_ms=p95([c.latency_ms for c in calls]),
        wrong=sorted(set(wrong)),
        left_out_ok=left_out_ok,
        left_out_total=left_out_total,
        go_relevant_ok=go_relevant_ok,
        go_relevant_total=go_relevant_total,
    )


def _gate(ok: bool) -> str:
    return "pass" if ok else "FAIL"


def render_judge_report(reports: Sequence[JudgeReport], *, day: str) -> str:
    first = reports[0]
    lines = [
        f"# judge_relevance eval - {day}",
        "",
        f"{len(POSTINGS)} synthetic postings judged for 2 synthetic profiles and "
        f"{len(GO_POSTINGS)} for a third (a Python and Go back end engineer) in "
        f"batches of {BATCH}; prompt v{first.prompt_version}; {first.repeat} run(s) per model. "
        "An answer the app could not use counts as missed.",
        "",
        "Gate: precision >= 90%, recall >= 90%, 0 unusable answers, "
        "0 injection-affected decisions, every short role made only of words from its title, "
        "and on the Python and Go profile at least 95% of the front end, mobile, QA and "
        "other-stack roles left out and at least 95% of the relevant roles kept.",
        "",
        "## Summary",
        "",
        "| model | tier | precision | recall | unusable | injection-affected | consistency "
        "| roles in title | tokens / job | p95 latency (ms) | left out (SC-008) "
        "| Go profile recall | gate |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.model} | {r.tier} | {r.precision:.1%} | {r.recall:.1%} | {r.unusable} "
            f"| {r.injection_affected} | {r.consistency:.1%} | {r.roles_in_title}/{r.roles_given} "
            f"| {r.tokens_per_job} "
            f"| {r.p95_ms} | {r.left_out_rate:.1%} ({r.left_out_ok}/{r.left_out_total}) "
            f"| {r.go_recall:.1%} ({r.go_relevant_ok}/{r.go_relevant_total}) | {_gate(r.passes)} |"
        )
    lines += ["", "## Wrong decisions", ""]
    for r in reports:
        lines.append(f"### {r.model}")
        lines += [f"- {w}" for w in r.wrong] or ["- none"]
        lines.append("")
    return "\n".join(lines)
