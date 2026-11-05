"""Structured JSON logging that never writes secrets or resume text.

Redaction (FR-029, constitution VIII):

* any ``SecretStr`` value, wherever it appears in ``extra`` fields;
* every configured secret (the API key) inside messages, field values and
  tracebacks, plus anything shaped like an OpenAI key (``sk-…``);
* the values of fields named ``text``, ``resume_text``, ``masked_text``,
  ``prompt`` or ``content``, at any nesting depth.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import IO, Any, Final

from pydantic import SecretStr

REDACTED: Final = "[REDACTED]"
SENSITIVE_FIELDS: Final = frozenset({"text", "resume_text", "masked_text", "prompt", "content"})
_KEY_PATTERN: Final = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
_RESERVED: Final = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime"}
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ``ts``, ``level``, ``logger``, ``message`` + extras."""

    def __init__(self, secrets: Iterable[str | SecretStr | None] = ()) -> None:
        super().__init__()
        values = (s.get_secret_value() if isinstance(s, SecretStr) else s for s in secrets)
        # longest first so a secret containing another is replaced whole
        self._secrets = sorted({v for v in values if v}, key=len, reverse=True)

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return _KEY_PATTERN.sub(REDACTED, text)

    def _clean(self, value: Any, key: str | None = None) -> Any:
        if key is not None and key.lower() in SENSITIVE_FIELDS:
            return REDACTED
        if isinstance(value, SecretStr):
            return REDACTED
        if isinstance(value, str):
            return self._scrub(value)
        if isinstance(value, Mapping):
            return {str(k): self._clean(v, str(k)) for k, v in value.items()}
        if isinstance(value, list | tuple | set | frozenset):
            return [self._clean(v) for v in value]
        if value is None or isinstance(value, bool | int | float):
            return value
        return self._scrub(str(value))

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": self._scrub(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = self._clean(value, key)
        if record.exc_info:
            entry["exception"] = self._scrub(self.formatException(record.exc_info))
        if record.stack_info:
            entry["stack"] = self._scrub(self.formatStack(record.stack_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(
    secrets: Iterable[str | SecretStr | None] = (),
    level: str | int = "INFO",
    stream: IO[str] | None = None,
) -> None:
    """Send all logs (including uvicorn's) through one redacting JSON handler."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter(secrets))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        named = logging.getLogger(name)
        named.handlers = []
        named.propagate = True
