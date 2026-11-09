"""OpenAI adapter for the LLM port (Responses API).

* Native structured output (strict ``json_schema`` built from the Pydantic model); if the
  model rejects that, one retry in JSON mode with the schema in the instructions and a
  strict parse of the reply (constitution IV, degrade gracefully).
* Errors: no key -> ``AiUnavailable("key_missing")`` before any network call; 401/403 ->
  ``AiUnavailable("key_rejected")``; 429 with ``insufficient_quota`` ->
  ``AiUnavailable("out_of_credit", provider_message)``; other 429s, 5xx and timeouts ->
  ``RetryableLlmError``.
  Retrying is the job queue's business, so the SDK's own retries are off.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import httpx2
import openai
from pydantic import BaseModel, SecretStr, ValidationError

from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.port import (
    AiUnavailable,
    LlmRequest,
    LlmResult,
    RetryableLlmError,
    Usage,
)
from hiretitan.platform.security.outbound_allowlist import allowed_base_url

PROVIDER = "openai"
KeyCheck = Literal["working", "rejected", "unreachable"]
_TIMEOUT_SECONDS = 120.0


def _is_structured_output_unsupported(error: openai.BadRequestError) -> bool:
    text = str(error).lower()
    return "json_schema" in text or "structured" in text or "text.format" in text


def _error_message(error: openai.APIStatusError) -> str:
    """The provider's own wording from the response body (the SDK adds a prefix to its own)."""
    body = error.body
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return str(body["message"])
    return error.message


class OpenAiAdapter:
    provider = PROVIDER

    def __init__(
        self,
        api_key: SecretStr | None,
        catalog: ModelCatalog,
        *,
        http_client: httpx2.AsyncClient | None = None,
        on_key_rejected: Callable[[], Awaitable[None]] | None = None,
        on_out_of_credit: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._has_key = api_key is not None
        self._catalog = catalog
        self._on_key_rejected = on_key_rejected
        self._on_out_of_credit = on_out_of_credit
        self._client = openai.AsyncOpenAI(
            api_key=api_key.get_secret_value() if api_key else "unset",
            base_url=allowed_base_url("api.openai.com"),
            max_retries=0,
            timeout=_TIMEOUT_SECONDS,
            http_client=http_client,
        )

    async def generate[T: BaseModel](self, req: LlmRequest[T]) -> LlmResult[T]:
        if not self._has_key:
            raise AiUnavailable("key_missing")
        model = self._catalog.model_for(PROVIDER, req.tier)
        started = time.perf_counter()
        try:
            try:
                value, response = await self._structured(req, model)
            except openai.BadRequestError as error:
                if not _is_structured_output_unsupported(error):
                    return self._failure(model, started, f"The request was rejected: {error}")
                value, response = await self._json_mode(req, model)
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            if self._on_key_rejected is not None:
                await self._on_key_rejected()
            raise AiUnavailable("key_rejected") from None
        except openai.RateLimitError as error:
            # OpenAI answers 429 both for "slow down" and for "no credit left". Waiting does not
            # fix the second, so it ends the run with the provider's own message (R7).
            if error.code == "insufficient_quota":
                unavailable = AiUnavailable("out_of_credit", _error_message(error))
                if self._on_out_of_credit is not None and unavailable.provider_message:
                    await self._on_out_of_credit(unavailable.provider_message)
                raise unavailable from None
            raise RetryableLlmError(type(error).__name__) from None
        except (
            openai.InternalServerError,
            openai.APITimeoutError,
            openai.APIConnectionError,
        ) as error:
            raise RetryableLlmError(type(error).__name__) from None
        except ValidationError as error:
            return self._failure(model, started, str(error))
        usage = self._usage(response, model, started)
        if value is None:
            return LlmResult(
                None, "error", usage, PROVIDER, model, error="The model returned no usable output"
            )
        return LlmResult(value, "ok", usage, PROVIDER, model)

    def _input(self, req: LlmRequest[Any]) -> str:
        return "\n\n".join([req.prompt.user, *(block.text for block in req.untrusted_blocks)])

    async def _structured[T: BaseModel](
        self, req: LlmRequest[T], model: str
    ) -> tuple[T | None, Any]:
        response = await self._client.responses.parse(
            model=model,
            instructions=req.prompt.system,
            input=self._input(req),
            text_format=req.output_schema,
            max_output_tokens=req.max_output_tokens,
        )
        return response.output_parsed, response

    async def _json_mode[T: BaseModel](
        self, req: LlmRequest[T], model: str
    ) -> tuple[T | None, Any]:
        schema = json.dumps(req.output_schema.model_json_schema())
        response = await self._client.responses.create(
            model=model,
            instructions=f"{req.prompt.system}\n\nReply with one JSON object matching this "
            f"JSON schema and nothing else:\n{schema}",
            input=self._input(req),
            text={"format": {"type": "json_object"}},
            max_output_tokens=req.max_output_tokens,
        )
        return req.output_schema.model_validate_json(response.output_text), response

    def _usage(self, response: Any, model: str, started: float) -> Usage:
        raw = response.usage
        cached = getattr(getattr(raw, "input_tokens_details", None), "cached_tokens", 0) or 0
        base = Usage(
            input_tokens=raw.input_tokens if raw else 0,
            cached_input_tokens=cached if raw else 0,
            output_tokens=raw.output_tokens if raw else 0,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        return Usage(
            base.input_tokens,
            base.cached_input_tokens,
            base.output_tokens,
            self._catalog.cost(model, base),
            base.latency_ms,
        )

    def _failure[T: BaseModel](self, model: str, started: float, message: str) -> LlmResult[T]:
        usage = Usage(latency_ms=round((time.perf_counter() - started) * 1000))
        return LlmResult(None, "error", usage, PROVIDER, model, error=message)

    async def check_key(self) -> KeyCheck:
        """``GET /v1/models``: a free call that tells a working key from a rejected one."""
        try:
            await self._client.models.list()
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            return "rejected"
        except openai.OpenAIError:
            return "unreachable"
        return "working"
