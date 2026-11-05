"""Request-size limit for uploads, enforced before the body is spooled to disk (FR-001).

Starlette parses a multipart body completely before a route runs, so a size check inside the
route comes too late. This middleware answers 413 from the ``Content-Length`` header, and cuts
off a body that lies about its length (or has none) as soon as the limit is crossed.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hiretitan.platform.web.problems import ProblemError, problem


class BodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        path: str,
        limit: int,
        message: str = "The file is larger than 5 MB",
    ) -> None:
        self.app = app
        self.path = path
        self.limit = limit
        self.message = message

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.limit:
            await problem(413, self.message)(scope, receive, send)
            return
        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise ProblemError(413, self.message)
            return message

        await self.app(scope, counting_receive, send)
