"""LLM port types. T017 adds ``LlmPort`` and the request/result types to this module."""

from __future__ import annotations

from typing import Final

PAUSE_REASONS: Final = ("key_missing", "key_rejected", "budget_reached")


class AiUnavailable(Exception):
    """The AI cannot be used right now; ``reason`` is the run's ``pause_reason``."""

    def __init__(self, reason: str) -> None:
        if reason not in PAUSE_REASONS:
            raise ValueError(f"Unknown AI-unavailable reason: {reason!r}")
        super().__init__(f"AI unavailable: {reason}")
        self.reason = reason


class RetryableLlmError(Exception):
    """A transient provider failure (429, 5xx, timeout): the job retries."""
