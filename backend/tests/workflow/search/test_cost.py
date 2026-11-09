"""T059: what a full search costs in AI spend (SC-006).

The graph runs for real against a fake scanner. The fake model reports a price per judged job
taken from the committed relevance eval report, so this test breaks if the report gets worse or
the search starts judging far more jobs than planned (research R15: about 150 jobs, 40 companies).
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import LlmRequest, LlmResult, Usage
from hiretitan.search.application.ports import ScanOk
from hiretitan.search.infra.models import JobRow, SearchRunRow

REPORTS = Path(__file__).resolve().parents[3] / "evals" / "reports"
LIMIT = Decimal("0.25")
COMPANIES = 40
JOBS_PER_COMPANY = 4  # about 150 jobs pass the rules on a first full search (R15)
PER_CALL = 10


def cost_per_job_from_report() -> Decimal:
    """The ``fast`` model's ``cost / job`` in the newest committed relevance report."""
    report = sorted(REPORTS.glob("judge_relevance-*.md"))[-1].read_text("utf-8")
    header = next(line for line in report.splitlines() if line.startswith("| model |"))
    column = [cell.strip() for cell in header.strip("|").split("|")].index("cost / job")
    row = next(
        line for line in report.splitlines() if re.match(r"\|\s*[\w.-]+\s*\|\s*fast\s*\|", line)
    )
    return Decimal(row.strip("|").split("|")[column].strip().lstrip("$"))


class PricedLlm(FakeLlm):
    """Reports ``per_job`` dollars for every decision in an answer, as the real model bills."""

    def __init__(self, per_job: Decimal) -> None:
        super().__init__()
        self._per_job = per_job

    async def generate[T: BaseModel](self, req: LlmRequest[T]) -> LlmResult[T]:
        result = await super().generate(req)
        decisions: list[Any] = getattr(result.value, "decisions", [])
        usage = Usage(cost_usd=self._per_job * len(decisions))
        return LlmResult(result.value, result.outcome, usage, result.provider, result.model)


def answers(count: int) -> list[dict[str, Any]]:
    """Scripted answers for ``count`` jobs judged ``PER_CALL`` at a time."""
    steps = []
    for start in range(0, count, PER_CALL):
        size = min(PER_CALL, count - start)
        steps.append(
            {
                "decisions": [
                    {"ref": f"j{i}", "relevant": True, "reason": "Python backend role"}
                    for i in range(1, size + 1)
                ]
            }
        )
    return steps


async def test_SC006_full_search_cost_under_limit(env: Env) -> None:
    per_job = cost_per_job_from_report()
    llm = PricedLlm(per_job)
    assert env.deps.judge is not None
    env.deps.judge.llm = llm
    total = COMPANIES * JOBS_PER_COMPANY
    for number in range(COMPANIES):
        name = f"Company{number}"
        ref = await add_company(env, name)
        env.career_ops.script(
            ref,
            ScanOk(
                [
                    posting(f"Backend Engineer {job}", company=name.lower())
                    for job in range(JOBS_PER_COMPANY)
                ]
            ),
        )
    # batches of 8 companies = 32 jobs each: calls of 10, 10, 10 and 2 jobs
    per_batch = 8 * JOBS_PER_COMPANY
    for _ in range(COMPANIES // 8):
        for step in answers(per_batch):
            llm.add(step, task="judge_relevance")

    await go(env, await new_search(env, mode="rules_and_ai"))

    async with env.sessions() as session:
        run = (await session.scalars(select(SearchRunRow))).one()
        stored = await session.scalar(select(func.count()).select_from(JobRow))
    assert stored == total
    assert run.outcome == "finished"
    # the column keeps 4 decimals, so each of the batches may round by half of 0.0001
    assert abs(run.ai_cost_usd - per_job * total) <= Decimal("0.00005") * (COMPANIES // 8)
    assert run.ai_cost_usd < LIMIT
    # the cost is shown while the search runs, and jobs reach Explore batch by batch
    batches = [data for event, data in env.published if event == "search.batch_done"]
    assert len(batches) == COMPANIES // 8
    assert Decimal(str(batches[0]["ai_cost_usd"])) > 0
    assert batches[0]["added"] > 0
    assert batches[0]["added"] < total
