"""Run the ``outreach_drafts`` and ``tailor_resume`` evals (spec SC-003 to SC-006).

The prompts, the validation chain and the truthfulness checks are the real ones; only the
database is left out. The report lists the tiers side by side so the message tier can be chosen on
evidence (research R1): ``--models fast,strong``.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel

import hiretitan.prompts as hiretitan_prompts
from evals.drafts.cases import SEEDED_FABRICATIONS, DraftCase, build_cases
from hiretitan.drafts.domain.checks import TechTerms, check_text
from hiretitan.drafts.domain.facts import drafting_facts, years_of_experience
from hiretitan.drafts.domain.fallback import (
    connection_fallback,
    email_fallback,
    referral_fallback,
)
from hiretitan.drafts.domain.keywords import backed, match
from hiretitan.drafts.domain.recipient import fill
from hiretitan.drafts.domain.resume_doc import build_from_profile, document_text, plain_reorder
from hiretitan.drafts.domain.selection import allowed_names, select_facts
from hiretitan.drafts.domain.tailor_checks import check_choice
from hiretitan.drafts.workflow.tailor import _profile_block
from hiretitan.drafts_wiring import tech_terms
from hiretitan.platform.llm.infra.calls_repo import LlmCallRecord
from hiretitan.platform.llm.port import LlmPort, LlmRequest
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.validation import TaskSpec, ValidatedLlm
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.prompts.draft_connection_request.v1.checks import rule_errors as connection_rules
from hiretitan.prompts.draft_email.v1.checks import assemble as assemble_email
from hiretitan.prompts.draft_email.v1.checks import rule_errors as email_rules
from hiretitan.prompts.draft_referral_message.v1.checks import rule_errors as referral_rules
from hiretitan.prompts.tailor_resume.v1.checks import choice_of

OUTREACH: Final = "outreach_drafts"
TAILOR: Final = "tailor_resume"
TODAY: Final = date(2026, 11, 17)
P95_GOAL_MS: Final = {OUTREACH: 10_000, TAILOR: 60_000}
TONE_FIRST_TRY_MIN: Final = 0.95
_GERMAN = re.compile(r"\b(?:und|der|die|das|wir|sie|bei|fuer|suchen)\b", re.IGNORECASE)


def looks_german(text: str) -> bool:
    return len(_GERMAN.findall(text)) >= 2


@dataclass
class DraftReport:
    task: str
    model: str
    tier: str
    repeat: int
    drafts: int = 0
    first_try_ok: int = 0
    repaired: int = 0
    fell_back: int = 0
    fabrications: int = 0
    length_total: int = 0
    length_ok: int = 0
    referral_total: int = 0
    referral_first_try: int = 0
    language_total: int = 0
    language_ok: int = 0
    seeded_total: int = 0
    seeded_caught: int = 0
    tokens: int = 0
    latencies: list[int] = field(default_factory=list)
    keyword_before: list[float] = field(default_factory=list)
    keyword_after: list[float] = field(default_factory=list)
    wrong: list[str] = field(default_factory=list)

    @property
    def p95_ms(self) -> int:
        if not self.latencies:
            return 0
        ordered = sorted(self.latencies)
        return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]

    @property
    def refusal_rate(self) -> float:
        return (self.repaired + self.fell_back) / self.drafts if self.drafts else 0.0

    @property
    def referral_first_try_rate(self) -> float:
        return self.referral_first_try / self.referral_total if self.referral_total else 1.0

    @property
    def passes(self) -> bool:
        base = (
            self.fabrications == 0
            and self.seeded_caught == self.seeded_total
            and self.p95_ms <= P95_GOAL_MS[self.task]
        )
        if self.task == OUTREACH:
            return (
                base
                and self.length_ok == self.length_total
                and self.referral_first_try_rate >= TONE_FIRST_TRY_MIN
            )
        return base


def _registry() -> PromptRegistry:
    return PromptRegistry(Path(hiretitan_prompts.__file__).parent)


def seeded_detection(terms: TechTerms) -> tuple[int, int]:
    """How many of the planted fabrications the checks catch (must be all)."""
    case = build_cases()[0]
    facts = drafting_facts(case.profile)
    years = years_of_experience(case.profile, TODAY)
    caught = sum(
        1
        for text in SEEDED_FABRICATIONS
        if check_text(
            text,
            (),
            facts,
            tech_terms=terms,
            allowed_names=allowed_names(case.profile, case.company, case.title),
            years=years,
            context=f"{case.title} {case.company}",
        )
    )
    return caught, len(SEEDED_FABRICATIONS)


class _Run:
    """One model's pass over the cases: a validated chain that notes tokens and latency."""

    def __init__(self, llm: LlmPort, report: DraftReport, terms: TechTerms) -> None:
        self.report = report
        self.terms = terms
        self.prompts = _registry()

        async def record(call: LlmCallRecord) -> None:
            report.tokens += call.input_tokens + call.output_tokens
            report.latencies.append(call.latency_ms)

        self.chain = ValidatedLlm(llm, record, provider="openai")

    async def keywords(self, case: DraftCase) -> tuple[str, list[str], list[str]]:
        prompt = self.prompts.load("extract_job_keywords")
        schema: type[BaseModel] = prompt.output_schema
        text = sanitize(case.description).text
        request = LlmRequest(
            task="extract_job_keywords",
            prompt=prompt.render(job_block=delimit("job_posting", text).text),
            output_schema=prompt.output_schema,
            tier=prompt.version.tier,
            max_output_tokens=prompt.version.max_output_tokens,
        )
        answered = await self.chain.run(
            request,
            TaskSpec(
                fallback=lambda: schema.model_validate(
                    {"role_summary": "", "keywords": [], "must_have": []}
                )
            ),
        )
        value: Any = answered.value
        return value.role_summary, list(value.keywords), list(value.must_have)


async def _outreach_case(run: _Run, case: DraftCase, kind: str) -> None:
    report = run.report
    summary, keywords, must_have = await run.keywords(case)
    facts = drafting_facts(case.profile)
    years = years_of_experience(case.profile, TODAY)
    chosen = select_facts(facts, [*must_have, *keywords], 12)
    names = allowed_names(case.profile, case.company, case.title)
    context = f"{case.title} {case.company}"
    prompt_name = {
        "connection_request": "draft_connection_request",
        "referral_message": "draft_referral_message",
        "email": "draft_email",
    }[kind]
    prompt = run.prompts.load(prompt_name)
    schema: type[BaseModel] = prompt.output_schema
    room = 200 - (len(case.first_name) - len("{recipient_first_name}"))
    variables: dict[str, Any] = {
        "job_title": case.title,
        "company": case.company,
        "years": years,
        "job_block": delimit(
            "job_requirements",
            json.dumps(
                {"role_summary": summary, "must_have": must_have, "keywords": keywords[:20]}
            ),
        ).text,
        "facts_block": delimit(
            "profile_facts", json.dumps([{"id": f.id, "text": f.text} for f in chosen])
        ).text,
    }
    me = case.profile.contact.name
    spec: TaskSpec[Any]
    if kind == "connection_request":
        variables["char_budget"] = room
        base = connection_rules(case.first_name, 200)

        def rules(output: Any) -> list[str]:
            errors = base(output)
            if errors:
                return errors
            found = check_text(
                output.body, output.cited_fact_ids, facts, tech_terms=run.terms,
                allowed_names=names, years=years, context=context,
            )  # fmt: skip
            return [p.message for p in found]

        spec = TaskSpec(
            fallback=lambda: schema.model_validate(
                {
                    "body": connection_fallback(case.title, case.company, chosen, case.first_name),
                    "cited_fact_ids": [],
                }
            ),
            rules=rules,
        )
    elif kind == "email":
        base_e = email_rules(2400)

        def rules(output: Any) -> list[str]:
            errors = base_e(output)
            if errors:
                return errors
            whole = "\n".join((output.greeting, output.body, output.closing))
            found = check_text(
                whole, output.cited_fact_ids, facts, tech_terms=run.terms,
                allowed_names=names, years=years, context=context,
            )  # fmt: skip
            return [p.message for p in found]

        mail = email_fallback(case.title, case.company, chosen)
        spec = TaskSpec(
            fallback=lambda: schema.model_validate(
                {
                    "subject": mail.subject,
                    "greeting": mail.greeting,
                    "body": mail.body,
                    "closing": mail.closing,
                    "cited_fact_ids": [],
                }
            ),
            rules=rules,
        )
    else:
        base_r = referral_rules(2000)

        def rules(output: Any) -> list[str]:
            errors = base_r(output)
            if errors:
                return errors
            whole = "\n".join((output.greeting, output.body, output.easy_out, output.sign_off))
            found = check_text(
                whole, output.cited_fact_ids, facts, tech_terms=run.terms,
                allowed_names=names, years=years, context=context,
            )  # fmt: skip
            return [p.message for p in found]

        parts = referral_fallback(case.title, case.company, chosen)
        spec = TaskSpec(
            fallback=lambda: schema.model_validate(
                {
                    "greeting": parts.greeting,
                    "body": parts.body,
                    "easy_out": parts.easy_out,
                    "sign_off": parts.sign_off,
                    "cited_fact_ids": [],
                }
            ),
            rules=rules,
        )
    request = LlmRequest(
        task=prompt_name,
        prompt=prompt.render(**variables),
        output_schema=prompt.output_schema,
        tier=prompt.version.tier,
        max_output_tokens=prompt.version.max_output_tokens,
    )
    answered = await run.chain.run(request, spec)
    value: Any = answered.value
    if kind == "connection_request":
        template = value.body
    elif kind == "email":
        template = assemble_email(value.subject, value.greeting, value.body, value.closing)
    else:
        template = f"{value.greeting}\n\n{value.body}\n\n{value.easy_out}\n\n{value.sign_off}"
    text = fill(template, case.first_name, me)
    report.drafts += 1
    report.first_try_ok += answered.outcome == "ok"
    report.repaired += answered.outcome == "repaired"
    report.fell_back += answered.outcome == "fallback"
    if kind == "connection_request":
        report.length_total += 1
        report.length_ok += len(text) <= 200
    elif kind == "referral_message":
        report.referral_total += 1
        report.referral_first_try += answered.outcome == "ok"
    if case.language == "de":
        report.language_total += 1
        report.language_ok += not looks_german(text)
    if answered.outcome != "fallback":
        # an email's subject has its own rules; its capitalised words would be read as names
        checked = template.partition("\n\n")[2] if kind == "email" else template
        problems = check_text(
            checked, value.cited_fact_ids, facts, tech_terms=run.terms,
            allowed_names=names, years=years, context=context,
        )  # fmt: skip
        if problems:
            report.fabrications += 1
            report.wrong.append(f"{case.id}/{kind}: {problems[0].message}")


async def evaluate_outreach(
    llm: LlmPort,
    *,
    tier: str,
    model: str,
    repeat: int = 1,
    cases: Sequence[DraftCase] | None = None,
) -> DraftReport:
    terms = _terms()
    report = DraftReport(OUTREACH, model, tier, repeat)
    report.seeded_caught, report.seeded_total = seeded_detection(terms)
    run = _Run(llm, report, terms)
    for _ in range(repeat):
        for case in cases if cases is not None else build_cases():
            for kind in ("connection_request", "referral_message", "email"):
                await _outreach_case(run, case, kind)
    return report


async def _tailor_case(run: _Run, case: DraftCase) -> None:
    report = run.report
    prompt = run.prompts.load("tailor_resume")
    schema: type[BaseModel] = prompt.output_schema
    view = case.profile
    summary, keywords, must_have = await run.keywords(case)
    wanted_all = list(dict.fromkeys([*must_have, *keywords]))
    can = backed(wanted_all, view)
    facts = drafting_facts(view)
    years = years_of_experience(view, TODAY)
    names = allowed_names(view, case.company, case.title)
    fallback = plain_reorder(view, wanted_all)
    job_requirements = {
        "role_summary": summary,
        "must_have": must_have,
        "keywords_the_profile_can_support": [k for k in wanted_all if k in can],
    }
    request = LlmRequest(
        task="tailor_resume",
        prompt=prompt.render(
            job_title=case.title,
            company=case.company,
            years=years,
            job_block=delimit("job_requirements", json.dumps(job_requirements)).text,
            profile_block=_profile_block(view),
        ),
        output_schema=prompt.output_schema,
        tier=prompt.version.tier,
        max_output_tokens=prompt.version.max_output_tokens,
    )
    context = f"{case.title} {case.company}"

    def rules(output: Any) -> list[str]:
        found = check_choice(
            choice_of(output),
            view,
            facts,
            tech_terms=run.terms,
            allowed_names=names,
            years=years,
            context=context,
        )
        return [p.message for p in found]

    def fall_back() -> Any:
        empty = {"summary": fallback.summary, "experience": [], "skills": [], "project_ids": []}
        return schema.model_validate(empty)

    answered = await run.chain.run(request, TaskSpec(fallback=fall_back, rules=rules))
    report.drafts += 1
    report.first_try_ok += answered.outcome == "ok"
    report.repaired += answered.outcome == "repaired"
    report.fell_back += answered.outcome == "fallback"
    doc = (
        fallback
        if answered.outcome == "fallback"
        else build_from_profile(view, choice_of(answered.value))
    )
    before = match(wanted_all, document_text(build_from_profile(view, _blank(view))), can)
    after = match(wanted_all, document_text(doc), can)
    report.keyword_before.append(before.score)
    report.keyword_after.append(after.score)
    if case.language == "de":
        report.language_total += 1
        report.language_ok += not looks_german(doc.summary)


async def evaluate_tailor(
    llm: LlmPort,
    *,
    tier: str,
    model: str,
    repeat: int = 1,
    cases: Sequence[DraftCase] | None = None,
) -> DraftReport:
    terms = _terms()
    report = DraftReport(TAILOR, model, tier, repeat)
    report.seeded_caught, report.seeded_total = seeded_detection(terms)
    run = _Run(llm, report, terms)
    for _ in range(repeat):
        for case in cases if cases is not None else build_cases():
            await _tailor_case(run, case)
    return report


def _blank(view: Any) -> Any:
    from hiretitan.drafts.domain.resume_doc import ResumeChoice

    return ResumeChoice(summary=view.summary or "")


def _terms() -> TechTerms:
    from hiretitan.search.application.tables_seed import load_tech_names
    from hiretitan.seed_dir import resolve_seed_dir

    return tech_terms(load_tech_names(resolve_seed_dir() / "tech_names.yaml"))


def _avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}% ({part}/{whole})" if whole else "n/a"


def render_report(reports: Sequence[DraftReport], *, day: str) -> str:
    """Markdown with one column per tier, so the tiers can be compared (research R1)."""
    task = reports[0].task
    head = ["Measure", *(f"{r.tier} ({r.model})" for r in reports)]
    rows: list[list[str]] = [
        ["Drafts", *(str(r.drafts) for r in reports)],
        ["Accepted on the first try", *(_pct(r.first_try_ok, r.drafts) for r in reports)],
        ["Repaired once", *(str(r.repaired) for r in reports)],
        ["Plain template used", *(str(r.fell_back) for r in reports)],
        [
            "Refused for a good draft (repaired + template)",
            *(f"{r.refusal_rate:.0%}" for r in reports),
        ],
        ["Fabrications in accepted text (goal 0)", *(str(r.fabrications) for r in reports)],
        [
            "Seeded fabrications caught (goal 100%)",
            *(_pct(r.seeded_caught, r.seeded_total) for r in reports),
        ],
        [
            "Non-English posting, draft in profile language",
            *(_pct(r.language_ok, r.language_total) for r in reports),
        ],
        [f"p95 latency ms (goal {P95_GOAL_MS[task]})", *(str(r.p95_ms) for r in reports)],
        ["Tokens", *(str(r.tokens) for r in reports)],
    ]
    if task == OUTREACH:
        rows += [
            [
                "Connection requests within 200 characters",
                *(_pct(r.length_ok, r.length_total) for r in reports),
            ],
            [
                "Referral tone accepted first try (goal 95%)",
                *(_pct(r.referral_first_try, r.referral_total) for r in reports),
            ],
        ]
    else:
        rows += [
            ["Keyword match before", *(f"{_avg(r.keyword_before):.0%}" for r in reports)],
            ["Keyword match after", *(f"{_avg(r.keyword_after):.0%}" for r in reports)],
        ]
    rows.append(["Passes", *("yes" if r.passes else "NO" for r in reports)])
    lines = [f"# {task} eval, {day}", "", f"Repeat: {reports[0].repeat}", ""]
    lines.append("| " + " | ".join(head) + " |")
    lines.append("|" + "---|" * len(head))
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    wrong = [w for r in reports for w in r.wrong]
    if wrong:
        lines += ["", "## Accepted text that failed the checks", *(f"- {w}" for w in wrong[:20])]
    return "\n".join(lines) + "\n"
