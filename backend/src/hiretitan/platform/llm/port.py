"""The LLM port (architecture §5.1): what every provider adapter and the fake implement.

Workflows ask for a tier (``fast`` / ``strong``), never a model name.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel

PAUSE_REASONS: Final = ("key_missing", "key_rejected", "out_of_credit")

PROVIDER_MESSAGE_MAX: Final = 300

Tier = Literal["fast", "strong"]
Outcome = Literal["ok", "repaired", "fallback", "refused", "error"]


def _clean_message(message: str | None) -> str | None:
    """Make a provider message safe to store and show: control characters become spaces,
    runs of whitespace collapse, and the result is capped at ``PROVIDER_MESSAGE_MAX``."""
    if message is None:
        return None
    printable = "".join(ch if ch.isprintable() else " " for ch in message)
    return " ".join(printable.split())[:PROVIDER_MESSAGE_MAX]


class AiUnavailable(Exception):
    """The AI cannot be used right now; ``reason`` is the run's ``pause_reason``."""

    def __init__(self, reason: str, provider_message: str | None = None) -> None:
        if reason not in PAUSE_REASONS:
            raise ValueError(f"Unknown AI-unavailable reason: {reason!r}")
        super().__init__(f"AI unavailable: {reason}")
        self.reason = reason
        # The provider's own words (e.g. "You exceeded your current quota"), shown to the person.
        self.provider_message = _clean_message(provider_message)


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


# --- Chat with tools (002m research R1) --------------------------------------------------------
# ``generate`` returns one validated object. A chat turn needs text as it arrives and tool calls,
# so it has its own method. Tool arguments are validated by the caller against each action's
# model; this port only carries them.

ChatRole = Literal["person", "mikasa", "tool_call", "tool_result"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool the model may call: its name, what it does, and a JSON schema for its arguments."""

    name: str
    description: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One entry in the history sent to the model.

    ``person`` and ``mikasa`` carry ``text``; ``tool_call`` carries ``tool_call_id``,
    ``tool_name`` and ``arguments_json``; ``tool_result`` carries ``tool_call_id`` and the
    result as ``text`` (already wrapped as a data block by the caller).
    """

    role: ChatRole
    text: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_json: str | None = None


@dataclass(frozen=True, slots=True)
class ConverseRequest:
    task: str  # e.g. "mikasa_turn"; used for logging and the fake's script
    prompt: RenderedPrompt  # the system part is the instructions; ``user`` is unused
    messages: Sequence[ChatMessage]
    tools: Sequence[ToolSpec]
    tier: Tier
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class TurnEnd:
    """Always the last event of a ``converse`` call: what the caller logs."""

    usage: Usage
    provider: str
    model: str
    outcome: Outcome


ConverseEvent = TextDelta | ToolCall | TurnEnd


class ConversePort(Protocol):
    """Streams one model round: text pieces and tool calls, then ``TurnEnd``.

    Raises ``AiUnavailable`` and ``RetryableLlmError`` like ``generate``.
    """

    def converse(self, req: ConverseRequest) -> AsyncIterator[ConverseEvent]: ...
