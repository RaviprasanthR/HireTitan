"""The AI key from Settings (contracts/rest-api.md, "AI key"; 002c US6, FR-029, FR-030).

The key goes in, never out: no answer here or anywhere else holds it, only where it comes from
and (through ``GET /status``) whether it works. Saving or removing a key queues the usual key
check; once the worker finds a key working it resumes the runs a key problem had paused.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

from hiretitan.platform.llm.key_store import KeyStore, KeyStoreError
from hiretitan.platform.web.problems import ProblemError

FROM_ENV = "The key comes from OPENAI_API_KEY in .env. Change it there and restart HireTitan."
NO_STORE = "This install does not take an AI key here."


@dataclass(frozen=True)
class AiKeyApiDeps:
    keys: KeyStore | None  # None: the fake AI (end-to-end runs), nothing to set
    enqueue_key_check: Callable[[], Awaitable[None]]


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # the size is checked by the store; a cap here only stops absurd bodies before they are read
    key: str = Field(max_length=1000)


class KeySaved(BaseModel):
    key_source: Literal["page"]
    status: Literal["unknown"]


def create_ai_key_router(deps: AiKeyApiDeps) -> APIRouter:
    router = APIRouter(prefix="/settings", tags=["settings"])

    def store() -> KeyStore:
        if deps.keys is None:
            raise ProblemError(409, NO_STORE, reason="no_key_store")
        if deps.keys.from_environment:
            raise ProblemError(409, FROM_ENV, reason="key_from_environment")
        return deps.keys

    @router.put("/ai-key", status_code=202)
    async def save_key(body: KeyIn) -> KeySaved:
        keys = store()
        try:
            keys.save(body.key)
        except KeyStoreError as error:
            message = "A key is 20 to 300 characters with no spaces."
            raise ProblemError(
                422, message, reason="invalid_key", errors=[{"field": "key", "message": message}]
            ) from error
        await deps.enqueue_key_check()
        return KeySaved(key_source="page", status="unknown")

    @router.delete("/ai-key", status_code=204)
    async def remove_key() -> Response:
        store().remove()
        await deps.enqueue_key_check()  # the key is now missing: AI tasks pause, the banner says so
        return Response(status_code=204)

    return router
