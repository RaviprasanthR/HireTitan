"""Output schema for ``judge_relevance`` v1: one decision per job card."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Decision(Strict):
    ref: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    relevant: bool
    reason: Annotated[str, StringConstraints(min_length=1, max_length=160)]


class JudgeRelevanceOutput(Strict):
    decisions: list[Decision] = Field(max_length=10)


# The prompt registry loads the model named ``Output``.
Output = JudgeRelevanceOutput
