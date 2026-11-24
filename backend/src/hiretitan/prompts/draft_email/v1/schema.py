"""Output schema for ``draft_email`` v1 (002m)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailOutput(Strict):
    subject: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    greeting: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    body: Annotated[str, StringConstraints(min_length=1, max_length=1200)]
    closing: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    cited_fact_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=120)]] = Field(
        max_length=12
    )


# The prompt registry loads the model named ``Output``.
Output = EmailOutput
