"""Output schema for ``judge_relevance`` v2: one decision and one short role per job card."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Decision(Strict):
    ref: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    relevant: bool
    reason: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    # Optional so an answer without it is still usable; the job then shows the rule-based
    # short title.
    role: Annotated[str, StringConstraints(min_length=1, max_length=60)] | None = None


class JudgeRelevanceOutput(Strict):
    decisions: list[Decision] = Field(max_length=10)


# The prompt registry loads the model named ``Output``.
Output = JudgeRelevanceOutput
