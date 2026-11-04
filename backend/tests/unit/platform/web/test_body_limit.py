"""Upload bodies are cut off at the door, before Starlette spools them to disk (FR-001)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from hiretitan.platform.web.limits import BodyLimitMiddleware
from hiretitan.platform.web.problems import ProblemError

LIMIT = 1000
PATH = "/api/v1/resumes"


class Recorder:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        return int(self.messages[0]["status"])

    @property
    def body(self) -> dict[str, Any]:
        return json.loads(b"".join(m.get("body", b"") for m in self.messages[1:]))


def scope(*, method: str = "POST", path: str = PATH, length: int | None = None) -> Scope:
    headers = [(b"content-length", str(length).encode())] if length is not None else []
    return {"type": "http", "method": method, "path": path, "headers": headers}


async def never_read() -> Message:
    raise AssertionError("the body must not be read")


async def test_declared_length_over_limit_is_413_without_reading_the_body() -> None:
    reached: list[bool] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(True)

    out = Recorder()
    await BodyLimitMiddleware(app, path=PATH, limit=LIMIT)(scope(length=LIMIT + 1), never_read, out)

    assert out.status == 413
    assert out.body["detail"] == "The file is larger than 5 MB"
    assert reached == []


async def test_streamed_body_over_limit_is_cut_off_even_without_content_length() -> None:
    chunks = [{"type": "http.request", "body": b"x" * 600, "more_body": True}] * 3
    read: list[int] = []

    async def receive() -> Message:
        read.append(1)
        return chunks[len(read) - 1]

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            await receive()

    with pytest.raises(ProblemError) as caught:
        await BodyLimitMiddleware(app, path=PATH, limit=LIMIT)(scope(), receive, Recorder())

    assert caught.value.status == 413
    assert len(read) == 2  # stopped at the chunk that crossed the limit


async def test_other_paths_and_methods_are_untouched() -> None:
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["path"])

    mw = BodyLimitMiddleware(app, path=PATH, limit=LIMIT)
    await mw(scope(path="/api/v1/profile", length=10**9), never_read, Recorder())
    await mw(scope(method="GET", length=10**9), never_read, Recorder())

    assert seen == ["/api/v1/profile", PATH]
