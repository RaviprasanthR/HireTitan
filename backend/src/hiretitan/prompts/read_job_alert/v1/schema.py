"""Output schema for ``read_job_alert`` v1: the jobs an alert email announces.

A job names its link by the number it was shown (never an address of its own): an email, or a
planted instruction in it, cannot make the app open an address the email did not contain.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlertJobOut(Strict):
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    company: Annotated[str, StringConstraints(max_length=120)] | None = None
    location: Annotated[str, StringConstraints(max_length=120)] | None = None
    link_index: int = Field(ge=1, le=1000)


class ReadJobAlertOutput(Strict):
    jobs: list[AlertJobOut] = Field(max_length=30)


# The prompt registry loads the model named ``Output``.
Output = ReadJobAlertOutput
