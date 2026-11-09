"""Output schema for ``extract_jobs_from_page`` v1: the jobs a careers page lists."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FoundJob(Strict):
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    url: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    location: Annotated[str, StringConstraints(max_length=200)] | None = None


class ExtractJobsOutput(Strict):
    jobs: list[FoundJob] = Field(max_length=50)


# The prompt registry loads the model named ``Output``.
Output = ExtractJobsOutput
