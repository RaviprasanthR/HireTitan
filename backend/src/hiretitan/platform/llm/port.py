"""The LLM port (architecture §5.1): what every provider adapter, the fake and the budget
guard implement. Workflows ask for a tier (``fast`` / ``strong``), never a model name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, Literal, Protocol

from pydantic import BaseModel

PAUSE_REASONS: Final = ("key_missing", "key_rejected", "budget_reached")

Tier = Literal["fast", "strong"]
Outcome = Literal["ok", "repaired", "fallback", "refused", "budget_blocked", "error"]


class AiUnavailable(Exception):
    """The AI cannot be used right now; ``reason`` is the run's ``pause_reason``."""

    def __init__(self, reason: str) -> None:
        if reason not in PAUSE_REASONS:
            raise ValueError(f"Unknown AI-unavailable reason: {reason!r}")
        super().__init__(f"AI unavailable: {reason}")
        self.reason = reason


class RetryableLlmError(Exception):
    """A transient provider failure (429, 5xx, timeout): the job retries."""


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """A prompt version with its system and user parts already rendered (T018 builds these)."""

    name: str
    version: int
    system: str
    user: str


@dataclass(frozen=True, slots=True)
class UntrustedText:
    """Text from outside the app, already sanitized and delimited (architecture §6)."""

    label: str
    text: str


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    latency_ms: int = 0


@dataclass(frozen=True, slots=True)
class LlmRequest[T: BaseModel]:
    task: str  # e.g. "extract_profile"
    prompt: RenderedPrompt
    output_schema: type[T]
    tier: Tier
    max_output_tokens: int
    untrusted_blocks: list[UntrustedText] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LlmResult[T: BaseModel]:
    value: T | None
    outcome: Outcome
    usage: Usage
    provider: str
    model: str
    error: str | None = None  # why value is None, when the output could not be used


class LlmPort(Protocol):
    async def generate[T: BaseModel](self, req: LlmRequest[T]) -> LlmResult[T]: ...
