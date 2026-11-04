"""Validation chain for LLM output (architecture §5.2, constitution IV).

Order: schema parse -> per-task business rules -> optional task check (keeps a value and
reports what it dropped) -> safety (no URLs or emails the task did not allow).
On failure there is exactly one repair call that carries the error list; if that fails
too, the task's fallback is used. A failed AI step never raises and never loses data.
Every attempt is logged through the injected recorder (the calls repo in production).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ValidationError

from hiretitan.platform.llm.infra.calls_repo import LlmCallRecord
from hiretitan.platform.llm.port import (
    LlmPort,
    LlmRequest,
    LlmResult,
    Outcome,
    RenderedPrompt,
)

_URL: Final = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
_EMAIL: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TRAILING: Final = ".,;:!?"

Recorder = Callable[[LlmCallRecord], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Dropped:
    """Something removed from the output, and why (shown to the user where it matters)."""

    path: str
    reason: str
    item: str


@dataclass(frozen=True, slots=True)
class TaskSpec[T: BaseModel]:
    fallback: Callable[[], T]
    rules: Callable[[T], list[str]] | None = None
    check: Callable[[T], tuple[T, list[Dropped]]] | None = None
    allowed_links: frozenset[str] = frozenset()  # URLs and emails the task may output


@dataclass(frozen=True, slots=True)
class ValidatedResult[T: BaseModel]:
    value: T
    outcome: Outcome  # ok | repaired | fallback
    dropped: list[Dropped] = field(default_factory=list)


def _strip_unexpected(
    value: Any, allowed: frozenset[str], path: str, dropped: list[Dropped]
) -> Any:
    if isinstance(value, str):

        def drop(match: re.Match[str]) -> str:
            found = match.group(0).rstrip(_TRAILING)
            tail = match.group(0)[len(found) :]
            if found in allowed:
                return match.group(0)
            dropped.append(Dropped(path, "link or email not allowed here", found))
            return tail

        # Emails first: "bad@evil.example" must not be half-eaten by the URL rule.
        return re.sub(r"[ \t]{2,}", " ", _URL.sub(drop, _EMAIL.sub(drop, value))).strip()
    if isinstance(value, list):
        return [_strip_unexpected(v, allowed, f"{path}[{i}]", dropped) for i, v in enumerate(value)]
    if isinstance(value, dict):
        return {
            k: _strip_unexpected(v, allowed, f"{path}.{k}" if path else str(k), dropped)
            for k, v in value.items()
        }
    return value


class ValidatedLlm:
    def __init__(self, llm: LlmPort, recorder: Recorder, *, provider: str) -> None:
        self._llm = llm
        self._recorder = recorder
        self._provider = provider

    async def run[T: BaseModel](
        self, req: LlmRequest[T], spec: TaskSpec[T], *, run_id: Any = None
    ) -> ValidatedResult[T]:
        value, dropped, errors = await self._attempt(req, spec, "ok", run_id)
        if value is not None:
            return ValidatedResult(value, "ok", dropped)
        if errors is None:  # refused: a repair would not help
            return ValidatedResult(spec.fallback(), "fallback")
        value, dropped, errors = await self._attempt(
            self._repair_request(req, errors), spec, "repaired", run_id
        )
        if value is not None:
            return ValidatedResult(value, "repaired", dropped)
        return ValidatedResult(spec.fallback(), "fallback")

    @staticmethod
    def _repair_request[T: BaseModel](req: LlmRequest[T], errors: list[str]) -> LlmRequest[T]:
        notes = "\n".join(f"- {error}" for error in errors)
        user = f"{req.prompt.user}\n\nYour previous answer was not valid:\n{notes}\nAnswer again."
        return replace(
            req,
            prompt=RenderedPrompt(req.prompt.name, req.prompt.version, req.prompt.system, user),
        )

    async def _attempt[T: BaseModel](
        self, req: LlmRequest[T], spec: TaskSpec[T], success: Outcome, run_id: Any
    ) -> tuple[T | None, list[Dropped], list[str] | None]:
        """One call + checks. Returns (value, dropped, errors); errors None means refused."""
        result = await self._llm.generate(req)
        value, dropped, errors = self._check(result, spec)
        failed_outcome: Outcome = "fallback" if success == "repaired" else "error"
        if result.outcome == "refused":
            attempt_outcome: Outcome = "refused"
        else:
            attempt_outcome = success if value is not None else failed_outcome
        await self._log(req, result, attempt_outcome, run_id)
        return value, dropped, None if result.outcome == "refused" else errors

    def _check[T: BaseModel](
        self, result: LlmResult[T], spec: TaskSpec[T]
    ) -> tuple[T | None, list[Dropped], list[str]]:
        if result.value is None:
            return None, [], [result.error or f"no usable answer ({result.outcome})"]
        value = result.value
        if spec.rules is not None and (errors := spec.rules(value)):
            return None, [], errors
        dropped: list[Dropped] = []
        if spec.check is not None:
            value, dropped = spec.check(value)
        stripped: list[Dropped] = []
        cleaned = _strip_unexpected(value.model_dump(), spec.allowed_links, "", stripped)
        try:
            value = type(value).model_validate(cleaned)
        except ValidationError as exc:
            return None, [], [f"after removing disallowed links: {exc}"]
        return value, [*dropped, *stripped], []

    async def _log(
        self, req: LlmRequest[Any], result: LlmResult[Any], outcome: Outcome, run_id: Any
    ) -> None:
        usage = result.usage
        await self._recorder(
            LlmCallRecord(
                task=req.task,
                prompt_name=req.prompt.name,
                prompt_version=str(req.prompt.version),
                provider=result.provider or self._provider,
                model=result.model,
                input_tokens=usage.input_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost_usd,
                estimated_cost_usd=usage.cost_usd if usage.cost_usd else Decimal(0),
                latency_ms=usage.latency_ms,
                outcome=outcome,
                run_id=run_id,
            )
        )
