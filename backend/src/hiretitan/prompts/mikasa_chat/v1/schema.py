"""Mikasa's reply as stored (002m research R9). The model answers in text and tool calls through
``converse``; this model only states the bound the reply check enforces."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Output(BaseModel):
    text: str = Field(max_length=4000)
