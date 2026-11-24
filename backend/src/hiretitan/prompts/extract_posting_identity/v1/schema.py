"""Output schema for ``extract_posting_identity`` v1 (002m): the title and company of a post."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PostingIdentity(Strict):
    title: Annotated[str, StringConstraints(max_length=200)]
    company: Annotated[str, StringConstraints(max_length=120)]


# The prompt registry loads the model named ``Output``.
Output = PostingIdentity
