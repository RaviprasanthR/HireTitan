"""A scripted ``LlmPort`` for tests and ``HIRETITAN_LLM=fake`` (no network, no cost).

Each ``generate`` call consumes the next scripted step: a model instance, a dict (validated
against the request's schema; an invalid one gives an ``error`` result, like a real model
returning bad JSON), or an exception (raised). Every request is recorded in ``calls``.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from hiretitan.platform.llm.port import LlmRequest, LlmResult, Usage

Step = BaseModel | Mapping[str, Any] | BaseException


class FakeLlmScriptExhaustedError(AssertionError):
    """The test made more LLM calls than it scripted."""


class FakeLlm:
    provider = "fake"
    model = "fake-model"

    def __init__(
        self,
        script: Iterable[Step] = (),
        *,
        by_task: Mapping[str, Iterable[Step]] | None = None,
    ) -> None:
        self._queue: deque[Step] = deque(script)
        self._by_task: dict[str, deque[Step]] = defaultdict(deque)
        for task, steps in (by_task or {}).items():
            self._by_task[task].extend(steps)
        self.calls: list[LlmRequest[Any]] = []

    @classmethod
    def from_directory(cls, directory: Path) -> FakeLlm:
        """Load ``<task>.json`` files, each a list of outputs for that task, in order."""
        by_task = {
            path.stem: cast(list[Mapping[str, Any]], json.loads(path.read_text("utf-8")))
            for path in sorted(directory.glob("*.json"))
        }
        return cls(by_task=by_task)

    def _next(self, task: str) -> Step:
        if self._by_task.get(task):
            return self._by_task[task].popleft()
        if self._queue:
            return self._queue.popleft()
        raise FakeLlmScriptExhaustedError(f"No scripted output left for task {task!r}")

    async def generate[T: BaseModel](self, req: LlmRequest[T]) -> LlmResult[T]:
        self.calls.append(req)
        step = self._next(req.task)
        if isinstance(step, BaseException):
            raise step
        try:
            value = (
                step
                if isinstance(step, req.output_schema)
                else req.output_schema.model_validate(
                    step.model_dump() if isinstance(step, BaseModel) else step
                )
            )
        except ValidationError as exc:
            return LlmResult(None, "error", Usage(), self.provider, self.model, error=str(exc))
        return LlmResult(value, "ok", Usage(), self.provider, self.model)
