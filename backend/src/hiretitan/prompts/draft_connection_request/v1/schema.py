"""Output schema for ``draft_connection_request`` v1."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectionRequestOutput(Strict):
    body: Annotated[str, StringConstraints(min_length=1, max_length=400)]
    cited_fact_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=120)]] = Field(
        max_length=12
    )


# The prompt registry loads the model named ``Output``.
Output = ConnectionRequestOutput
