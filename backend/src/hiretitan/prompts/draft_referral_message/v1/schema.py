"""Output schema for ``draft_referral_message`` v1."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReferralMessageOutput(Strict):
    greeting: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    body: Annotated[str, StringConstraints(min_length=1, max_length=900)]
    easy_out: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    sign_off: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    cited_fact_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=120)]] = Field(
        max_length=12
    )


# The prompt registry loads the model named ``Output``.
Output = ReferralMessageOutput
