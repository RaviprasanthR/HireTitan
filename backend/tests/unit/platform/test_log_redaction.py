"""T010: structured JSON logs never contain keys or resume text (FR-029, constitution VIII)."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import SecretStr

from hiretitan.platform.security.logging import REDACTED, JsonFormatter, configure_logging

KEY = "sk-proj-AbCdEf0123456789xyzKEY"


@pytest.fixture
def log() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(secrets=[KEY]))
    logger = logging.getLogger("hiretitan.test.redaction")
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    yield logger, stream
    logger.handlers = []


def lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_FR029_key_never_logged(log: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = log
    logger.info("calling provider with key %s", KEY)
    logger.info("plain", extra={"api_key": SecretStr(KEY), "note": f"Bearer {KEY}"})
    logger.info("nested", extra={"request": {"headers": {"authorization": f"Bearer {KEY}"}}})
    try:
        raise RuntimeError(f"401 for key {KEY}")
    except RuntimeError:
        logger.exception("provider failed")

    output = stream.getvalue()
    assert KEY not in output
    assert REDACTED in output


def test_FR029_unconfigured_openai_style_key_is_masked(
    log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = log
    other = "sk-" + "Z" * 40
    logger.warning("leaked %s", other)
    assert other not in stream.getvalue()


@pytest.mark.parametrize("field", ["text", "resume_text", "masked_text", "prompt", "content"])
def test_constitution_VIII_resume_text_redacted(
    log: tuple[logging.Logger, io.StringIO], field: str
) -> None:
    logger, stream = log
    resume = "Jane Example, 12 Sample Street, jane@example.com"
    logger.info("parsed", extra={field: resume, "chars": len(resume)})
    logger.info("call", extra={"payload": {field: resume}})

    output = stream.getvalue()
    assert "Jane Example" not in output
    first = lines(stream)[0]
    assert first[field] == REDACTED
    assert first["chars"] == len(resume)


def test_log_lines_are_structured_json(log: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = log
    logger.info("run %s moved", "r1", extra={"run_id": "r1", "status": "running"})
    record = lines(stream)[0]
    assert record["level"] == "INFO"
    assert record["logger"] == "hiretitan.test.redaction"
    assert record["message"] == "run r1 moved"
    assert record["run_id"] == "r1"
    assert record["status"] == "running"
    assert record["ts"].endswith("Z")


def test_configure_logging_registers_key_from_settings() -> None:
    stream = io.StringIO()
    configure_logging(secrets=[SecretStr(KEY), None], level="INFO", stream=stream)
    try:
        logging.getLogger("hiretitan.other").info("key=%s", KEY)
        assert KEY not in stream.getvalue()
        assert lines(stream)[0]["message"] == f"key={REDACTED}"
    finally:
        logging.getLogger().handlers = []
