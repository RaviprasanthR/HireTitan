"""The topic check's answer (002m FR-030): strict and bounded, so nothing the message says can
reach the main assistant through it."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Output(BaseModel):
    on_topic: bool
    reason: str = Field(max_length=120)
