"""Output schema for ``extract_job_keywords`` v1."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobKeywordsOutput(Strict):
    role_summary: Annotated[str, StringConstraints(max_length=160)]
    keywords: list[Annotated[str, StringConstraints(min_length=1, max_length=40)]] = Field(
        max_length=30
    )
    must_have: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        max_length=10
    )


# The prompt registry loads the model named ``Output``.
Output = JobKeywordsOutput
