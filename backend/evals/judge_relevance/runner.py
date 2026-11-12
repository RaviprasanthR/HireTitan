"""Run the ``judge_relevance`` eval: score the model's yes/no decisions against the labels (T027).

Every profile sees every posting in batches of 10, exactly as the search sends them. A batch the
app could not use (after one repair) counts as ``unusable`` and as missed answers for recall.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel

import hiretitan.prompts as hiretitan_prompts
from evals.judge_relevance.cases import POSTINGS, PROFILES, Posting
from hiretitan.platform.llm.infra.calls_repo import LlmCallRecord
from hiretitan.platform.llm.port import LlmPort, LlmRequest
from hiretitan.platform.llm.prompts import LoadedPrompt, PromptRegistry
from hiretitan.platform.llm.validation import TaskSpec, ValidatedLlm
from hiretitan.prompts.judge_relevance.v2.checks import role_words_outside, rule_errors
from hiretitan.search.application.judge_prompt import render_judge_prompt
from hiretitan.search.domain.cards import JobCardInput
from hiretitan.search.domain.normalize import normalize_job

PROMPT_NAME: Final = "judge_relevance"
PROVIDER: Final = "openai"
BATCH: Final = 10
PRECISION_MIN: Final = 0.90
RECALL_MIN: Final = 0.90


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

    @property
    def tokens_per_job(self) -> int:
        return self.tokens // self.decisions if self.decisions else 0

    @property
    def passes(self) -> bool:
        return (
            self.precision >= PRECISION_MIN
            and self.recall >= RECALL_MIN
            and self.unusable == 0
            and self.injection_affected == 0
            and self.roles_in_title == self.roles_given
        )


def _registry() -> PromptRegistry:
    return PromptRegistry(Path(hiretitan_prompts.__file__).parent)


def _label(profile: str, posting: Posting) -> bool:
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
    )


def _batches() -> list[list[Posting]]:
    return [list(POSTINGS[i : i + BATCH]) for i in range(0, len(POSTINGS), BATCH)]


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


async def evaluate_judge(llm: LlmPort, *, tier: str, model: str, repeat: int = 1) -> JudgeReport:
    prompt = _registry().load(PROMPT_NAME)
    schema: type[BaseModel] = prompt.output_schema
    calls: list[LlmCallRecord] = []

    async def record(call: LlmCallRecord) -> None:
        calls.append(call)

    chain = ValidatedLlm(llm, record, provider=PROVIDER)
    # (profile, posting id) -> the answer of each repeat; None = unusable
    answers: dict[tuple[str, str], list[bool | None]] = defaultdict(list)
    roles_given = roles_in_title = 0
    for _ in range(repeat):
        for profile in PROFILES:
            for batch in _batches():
                request, refs = _request(prompt, profile, batch, tier)
                result = await chain.run(
                    request,
                    TaskSpec(
                        fallback=lambda: schema.model_validate({"decisions": []}),
                        rules=rule_errors(refs, [p.title for p in batch]),
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
                            roles_in_title += not role_words_outside(d.role, titles[d.ref])
                for ref, posting in zip(refs, batch, strict=True):
                    answers[(profile, posting.id)].append(said.get(ref))

    by_id = {p.id: p for p in POSTINGS}
    true_pos = false_pos = false_neg = unusable = affected = 0
    wrong: list[str] = []
    for (profile, pid), given in answers.items():
        posting = by_id[pid]
        want = _label(profile, posting)
        for got in given:
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
    )


def _gate(ok: bool) -> str:
    return "pass" if ok else "FAIL"


def render_judge_report(reports: Sequence[JudgeReport], *, day: str) -> str:
    first = reports[0]
    lines = [
        f"# judge_relevance eval - {day}",
        "",
        f"{len(POSTINGS)} synthetic postings judged for {len(PROFILES)} synthetic profiles in "
        f"batches of {BATCH}; prompt v{first.prompt_version}; {first.repeat} run(s) per model. "
        "An answer the app could not use counts as missed.",
        "",
        "Gate: precision >= 90%, recall >= 90%, 0 unusable answers, "
        "0 injection-affected decisions, every short role made only of words from its title.",
        "",
        "## Summary",
        "",
        "| model | tier | precision | recall | unusable | injection-affected | consistency "
        "| roles in title | tokens / job | p95 latency (ms) | gate |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.model} | {r.tier} | {r.precision:.1%} | {r.recall:.1%} | {r.unusable} "
            f"| {r.injection_affected} | {r.consistency:.1%} | {r.roles_in_title}/{r.roles_given} "
            f"| {r.tokens_per_job} "
            f"| {r.p95_ms} | {_gate(r.passes)} |"
        )
    lines += ["", "## Wrong decisions", ""]
    for r in reports:
        lines.append(f"### {r.model}")
        lines += [f"- {w}" for w in r.wrong] or ["- none"]
        lines.append("")
    return "\n".join(lines)
