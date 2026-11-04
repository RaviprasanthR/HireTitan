"""Eval runner: ``python -m evals.run extract_profile --models fast,strong[,<model>] [--yes]``.

Runs the real pipeline pieces (parse, sanitize, mask, render prompt, validate and ground) on
the synthetic cases and scores the answer against ``expected/*.yaml`` (SC-003). Real models cost
money, so the runner prints an estimate first and does nothing without ``--yes``.
"""

from __future__ import annotations

import argparse
import asyncio
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel

import hiretitan.prompts as hiretitan_prompts
from evals.extract_profile.cases import CASES_DIR, EXPECTED_DIR
from hiretitan.platform.llm.infra.calls_repo import LlmCallRecord
from hiretitan.platform.llm.models import ModelCatalog, UnknownModelError
from hiretitan.platform.llm.port import LlmPort, LlmRequest
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.validation import ValidatedLlm
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.mask_contacts import mask_contacts
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.profile.infra.parsing.docx import parse_docx
from hiretitan.profile.infra.parsing.pdf import parse_pdf
from hiretitan.profile.workflow.nodes import PROMPT_NAME, extraction_task_spec

REPORTS_DIR: Final = Path(__file__).resolve().parent / "reports"
FIELDS: Final = ("employers", "titles", "dates", "skills", "education")
PROVIDER: Final = "openai"
SC003_TARGET: Final = 0.90
SC007_MAX_USD: Final = Decimal("0.05")
CHARS_PER_TOKEN: Final = 3  # a deliberately pessimistic estimate; the real count is lower
_PER_MILLION: Final = Decimal(1_000_000)


# ---- cases and scoring --------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Case:
    path: Path
    expected: dict[str, Any]


def load_cases(cases_dir: Path = CASES_DIR, expected_dir: Path = EXPECTED_DIR) -> list[Case]:
    cases = []
    for expected_file in sorted(expected_dir.glob("*.yaml")):
        data = yaml.safe_load(expected_file.read_text("utf-8"))
        cases.append(Case(cases_dir / expected_file.name.removesuffix(".yaml"), data))
    return cases


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _ym(value: dict[str, Any] | None) -> str | None:
    if not value or not value.get("month"):
        return None
    return f"{value['year']:04d}-{value['month']:02d}"


def facts_of(extraction: dict[str, Any]) -> dict[str, list[str]]:
    """The five scored fields out of an ``ExtractedProfile`` dump."""
    experience = extraction.get("experience", [])
    dates = [d for e in experience for d in (_ym(e.get("start")), _ym(e.get("end"))) if d]
    return {
        "employers": [e["employer"] for e in experience],
        "titles": [e["title"] for e in experience],
        "dates": dates,
        "skills": list(extraction.get("skills", [])),
        "education": [e["institution"] for e in extraction.get("education", [])],
    }


@dataclass(frozen=True, slots=True)
class CaseScore:
    counts: dict[str, tuple[int, int, int]]  # field -> (hits, extracted, expected)
    missed: dict[str, list[str]] = field(default_factory=dict)
    extra: dict[str, list[str]] = field(default_factory=dict)


def score_case(expected: dict[str, Any], got: dict[str, Any]) -> CaseScore:
    counts: dict[str, tuple[int, int, int]] = {}
    missed: dict[str, list[str]] = {}
    extra: dict[str, list[str]] = {}
    for name in FIELDS:
        want = {_norm(str(v)) for v in expected.get(name, [])}
        have = {_norm(str(v)) for v in got.get(name, [])}
        counts[name] = (len(want & have), len(have), len(want))
        if want - have:
            missed[name] = sorted(want - have)
        if have - want:
            extra[name] = sorted(have - want)
    return CaseScore(counts, missed, extra)


@dataclass(frozen=True, slots=True)
class FieldScore:
    precision: float
    recall: float


@dataclass(frozen=True, slots=True)
class CaseResult:
    name: str
    score: CaseScore
    outcome: str


@dataclass(frozen=True, slots=True)
class ModelReport:
    model: str
    tier: str
    fields: dict[str, FieldScore]
    overall: FieldScore
    cases: list[CaseResult]
    cost_usd: Decimal
    p95_ms: int
    failed_cases: int
    prompt_version: int


def _ratio(hits: int, total: int, *, empty: float) -> float:
    return hits / total if total else empty


def aggregate(scores: Sequence[CaseScore]) -> tuple[dict[str, FieldScore], FieldScore]:
    """Micro-averaged: counts are summed over all cases, then divided."""
    fields = {}
    all_hits = all_have = all_want = 0
    for name in FIELDS:
        hits = sum(s.counts[name][0] for s in scores)
        have = sum(s.counts[name][1] for s in scores)
        want = sum(s.counts[name][2] for s in scores)
        fields[name] = FieldScore(_ratio(hits, have, empty=1.0), _ratio(hits, want, empty=1.0))
        all_hits, all_have, all_want = all_hits + hits, all_have + have, all_want + want
    overall = FieldScore(
        _ratio(all_hits, all_have, empty=1.0), _ratio(all_hits, all_want, empty=1.0)
    )
    return fields, overall


def p95(values: Sequence[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


# ---- running one model --------------------------------------------------------------------
def _registry() -> PromptRegistry:
    return PromptRegistry(Path(hiretitan_prompts.__file__).parent)


@dataclass(frozen=True, slots=True)
class Prepared:
    request: LlmRequest[Any]
    clean_text: str
    schema: type[BaseModel]


def prepare(case: Case, tier: str = "fast") -> Prepared:
    """Parse, sanitize, mask and render the prompt exactly as the ingest workflow does."""
    data = case.path.read_bytes()
    doc = parse_pdf(data) if case.path.suffix == ".pdf" else parse_docx(data)
    clean = sanitize(doc.visible_text)
    masked = mask_contacts(clean.text, default_region="IN")
    prompt = _registry().load(PROMPT_NAME)
    block = delimit("resume", masked.text)
    request = LlmRequest(
        task=PROMPT_NAME,
        prompt=prompt.render(resume_block=block.text),
        output_schema=prompt.output_schema,
        tier=tier,  # type: ignore[arg-type]
        max_output_tokens=prompt.version.max_output_tokens,
        untrusted_blocks=[],
    )
    return Prepared(request, clean.text, prompt.output_schema)


async def evaluate(llm: LlmPort, cases: Sequence[Case], *, tier: str, model: str) -> ModelReport:
    calls: list[LlmCallRecord] = []

    async def record(call: LlmCallRecord) -> None:
        calls.append(call)

    chain = ValidatedLlm(llm, record, provider=PROVIDER)
    results: list[CaseResult] = []
    for case in cases:
        prepared = prepare(case, tier)
        try:
            outcome = await chain.run(
                prepared.request, extraction_task_spec(prepared.schema, prepared.clean_text)
            )
        except Exception:  # a provider error must not lose the other cases' results
            results.append(CaseResult(case.path.name, score_case(case.expected, {}), "error"))
            continue
        got = facts_of(outcome.value.model_dump())
        results.append(CaseResult(case.path.name, score_case(case.expected, got), outcome.outcome))
    fields, overall = aggregate([r.score for r in results])
    return ModelReport(
        model=model,
        tier=tier,
        fields=fields,
        overall=overall,
        cases=results,
        cost_usd=sum((c.cost_usd for c in calls), Decimal(0)),
        p95_ms=p95([c.latency_ms for c in calls]),
        failed_cases=sum(1 for r in results if r.outcome in ("fallback", "error")),
        prompt_version=_registry().load(PROMPT_NAME).version.version,
    )


# ---- cost estimate ------------------------------------------------------------------------
def estimate_cost(
    cases: Sequence[Case], model: str, catalog: ModelCatalog | None = None
) -> Decimal:
    """Upper-bound USD for one run over ``cases``: pessimistic input tokens plus full output."""
    price = (catalog or ModelCatalog.load()).price(model)
    total = Decimal(0)
    for case in cases:
        request = prepare(case).request
        tokens = (len(request.prompt.system) + len(request.prompt.user)) // CHARS_PER_TOKEN + 1
        total += (tokens * price.input + request.max_output_tokens * price.output) / _PER_MILLION
    return total


# ---- report -------------------------------------------------------------------------------
def render_report(reports: Sequence[ModelReport], *, day: str, case_count: int) -> str:
    lines = [
        f"# extract_profile eval - {day}",
        "",
        f"{case_count} synthetic resumes; prompt v{reports[0].prompt_version}. Scores are "
        "micro-averaged over all cases; an answer the app could not use counts as empty.",
        "",
        "## Summary",
        "",
        "| model | tier | precision | recall | SC-003 (>= 90%) | cost / resume | SC-007 (< $0.05) "
        "| p95 latency (ms) | unusable |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        per_resume = r.cost_usd / case_count if case_count else Decimal(0)
        lines.append(
            f"| {r.model} | {r.tier} | {r.overall.precision:.1%} | {r.overall.recall:.1%} "
            f"| {'pass' if r.overall.recall >= SC003_TARGET else 'FAIL'} "
            f"| ${per_resume:.4f} | {'pass' if per_resume < SC007_MAX_USD else 'FAIL'} "
            f"| {r.p95_ms} | {r.failed_cases} |"
        )
    lines += ["", "## Precision / recall by field", ""]
    lines += ["| model | " + " | ".join(FIELDS) + " |", "|---|" + "---|" * len(FIELDS)]
    for r in reports:
        cells = " | ".join(
            f"{r.fields[f].precision:.0%} / {r.fields[f].recall:.0%}" for f in FIELDS
        )
        lines.append(f"| {r.model} | {cells} |")
    lines += ["", "## Misses and extras by case", ""]
    for r in reports:
        lines.append(f"### {r.model}")
        any_issue = False
        for c in r.cases:
            if c.score.missed or c.score.extra or c.outcome != "ok":
                any_issue = True
                lines.append(f"- **{c.name}** ({c.outcome})")
                lines += [f"  - missed {k}: {', '.join(v)}" for k, v in c.score.missed.items()]
                lines += [f"  - extra {k}: {', '.join(v)}" for k, v in c.score.extra.items()]
        if not any_issue:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines)


# ---- command line -------------------------------------------------------------------------
def resolve_model(spec: str, catalog: ModelCatalog) -> tuple[str, str]:
    """``fast`` / ``strong`` -> that tier's model; otherwise a model name in ``models.yaml``."""
    if spec in ("fast", "strong"):
        return spec, catalog.model_for(PROVIDER, spec)  # type: ignore[arg-type]
    if spec in catalog.prices:
        return "fast", spec
    raise UnknownModelError(
        f"{spec!r} is not a tier or a model in models.yaml. Add it there with a price checked "
        "against the provider's pricing page, then run again."
    )


def _real_llm_for(catalog: ModelCatalog) -> Callable[[str], LlmPort]:
    from hiretitan.platform.config.settings import Settings
    from hiretitan.platform.llm.openai_adapter import OpenAiAdapter

    def build(model: str) -> LlmPort:
        key = Settings().openai_api_key
        if key is None:
            raise SystemExit("OPENAI_API_KEY is not set (put it in .env).")
        tiers = {PROVIDER: {**catalog.tiers[PROVIDER], "fast": model, "strong": model}}
        return OpenAiAdapter(key, replace(catalog, tiers=tiers))

    return build


def main(
    argv: Sequence[str] | None = None,
    *,
    llm_for: Callable[[str], LlmPort] | None = None,
    today: Callable[[], str] = lambda: datetime.now(UTC).date().isoformat(),
) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run")
    parser.add_argument("eval", choices=["extract_profile"])
    parser.add_argument("--models", default="fast", help="comma list of tiers or model names")
    parser.add_argument("--yes", action="store_true", help="confirm the estimated cost")
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)

    catalog = ModelCatalog.load()
    cases = load_cases()
    try:
        specs = [resolve_model(s.strip(), catalog) for s in args.models.split(",") if s.strip()]
    except UnknownModelError as exc:
        print(f"Error: {exc}")
        return 2

    estimates = [estimate_cost(cases, model, catalog) for _, model in specs]
    print(f"Estimated cost (upper bound, {len(cases)} resumes per model):")
    for (label, model), estimate in zip(specs, estimates, strict=True):
        print(f"  {label} ({model}): up to ${estimate:.2f}")
    print(f"  total: up to ${sum(estimates, Decimal(0)):.2f}")
    if not args.yes:
        print("Nothing was sent. Re-run with --yes to run the eval.")
        return 2

    build = llm_for or _real_llm_for(catalog)
    reports = [
        asyncio.run(evaluate(build(model), cases, tier=label, model=model))
        for label, model in specs
    ]
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    out = args.reports_dir / f"extract_profile-{today()}.md"
    out.write_text(render_report(reports, day=today(), case_count=len(cases)), encoding="utf-8")
    print(f"Report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
