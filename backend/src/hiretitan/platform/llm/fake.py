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

from hiretitan.platform.llm.port import AiUnavailable, LlmRequest, LlmResult, Usage

Step = BaseModel | Mapping[str, Any] | BaseException


KEY_STATUS_FILE = "key_status"


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
        control_dir: Path | None = None,
    ) -> None:
        self._control_dir = control_dir
        self._queue: deque[Step] = deque(script)
        self._by_task: dict[str, deque[Step]] = defaultdict(deque)
        for task, steps in (by_task or {}).items():
            self._by_task[task].extend(steps)
        self.calls: list[LlmRequest[Any]] = []

    def add(self, *steps: Step, task: str | None = None) -> None:
        """Queue more scripted steps (for ``task`` only, or for any task)."""
        (self._by_task[task] if task else self._queue).extend(steps)

    @classmethod
    def from_directory(cls, directory: Path) -> FakeLlm:
        """Load ``<task>.json`` files, each a list of outputs for that task, in order."""
        by_task = {
            path.stem: cast(list[Mapping[str, Any]], json.loads(path.read_text("utf-8")))
            for path in sorted(directory.glob("*.json"))
        }
        return cls(by_task=by_task, control_dir=directory)

    def key_status(self) -> str:
        """``working`` unless the control file ``key_status`` in the script folder says
        ``missing`` or ``rejected``. End-to-end runs write it to play out a key problem."""
        if self._control_dir is None:
            return "working"
        try:
            value = (self._control_dir / KEY_STATUS_FILE).read_text("utf-8").strip()
        except FileNotFoundError:
            return "working"
        return value if value in ("missing", "rejected") else "working"

    def _next(self, task: str) -> Step:
        if self._by_task.get(task):
            return self._by_task[task].popleft()
        if self._queue:
            return self._queue.popleft()
        raise FakeLlmScriptExhaustedError(f"No scripted output left for task {task!r}")

    async def generate[T: BaseModel](self, req: LlmRequest[T]) -> LlmResult[T]:
        self.calls.append(req)
        blocked = self.key_status()
        if blocked != "working":
            raise AiUnavailable(f"key_{blocked}")  # before the script is touched
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
