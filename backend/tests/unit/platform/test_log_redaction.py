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


def test_FR003_the_sign_in_callback_address_is_logged_without_its_code(
    log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = log
    logger.info(
        "GET /api/v1/mail/google/callback?code=4%2F0AXsynthetic&state=abc123&scope=x HTTP/1.1"
    )

    out = stream.getvalue()
    assert "4%2F0AXsynthetic" not in out
    assert "abc123" not in out
    assert "/api/v1/mail/google/callback?code=[REDACTED]&state=[REDACTED]&scope=x" in out


def test_FR003_settings_list_every_secret_for_the_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    from hiretitan.platform.config.settings import Settings

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-0123456789abcdef0123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "synthetic-id.invalid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "GOCSPX-synthetic-secret-0001")

    values = {s.get_secret_value() for s in Settings(_env_file=None).secrets() if s is not None}  # type: ignore[call-arg]

    assert {"sk-test-0123456789abcdef0123", "synthetic-id.invalid"} <= values
    assert "GOCSPX-synthetic-secret-0001" in values


def test_FR003_a_secret_registered_later_is_scrubbed(
    log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = log
    formatter = logger.handlers[0].formatter
    assert isinstance(formatter, JsonFormatter)
    refresh = "an-opaque-refresh-value-with-no-known-shape"

    formatter.register(refresh)
    logger.info(
        "token is %s and encoded %s", refresh, "an-opaque-refresh-value-with-no-known-shape"
    )

    assert refresh not in stream.getvalue()


def test_FR003_a_secret_registered_on_the_installed_handler_is_scrubbed() -> None:
    from hiretitan.platform.security.logging import register_secret

    stream = io.StringIO()
    configure_logging([], stream=stream)
    register_secret("late-client-secret-value-123")

    logging.getLogger("hiretitan.test.late").info("saw late-client-secret-value-123")

    assert "late-client-secret-value-123" not in stream.getvalue()


@pytest.mark.parametrize(
    "name", ["token", "client_secret", "code_verifier", "client_id", "refresh_token"]
)
def test_FR003_oauth_query_values_are_scrubbed(
    log: tuple[logging.Logger, io.StringIO], name: str
) -> None:
    logger, stream = log

    logger.info("GET /x?%s=abc123def456&other=1 HTTP/1.1", name)

    assert "abc123def456" not in stream.getvalue()
    assert "other=1" in stream.getvalue()


def test_FR003_url_encoded_secrets_are_scrubbed() -> None:
    formatter = JsonFormatter(secrets=["a b/c+d=secret"])
    record = logging.LogRecord("x", logging.INFO, "", 0, "q=a%20b%2Fc%2Bd%3Dsecret", None, None)

    assert "secret" not in formatter.format(record)


def test_FR003_mapping_keys_and_secret_looking_field_names_are_scrubbed(
    log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = log

    logger.info(
        "x",
        extra={
            "gmail_refresh_token": "plain-value-1",
            "my_client_secret_copy": "plain-value-2",
            "data": {KEY: "v", "Authorization-Header": "plain-value-3"},
        },
    )

    out = stream.getvalue()
    assert "plain-value" not in out
    assert KEY not in out


def test_FR003_http_client_loggers_do_not_print_request_urls() -> None:
    configure_logging([], stream=io.StringIO())

    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING
