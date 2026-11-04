"""API composition root: ``uvicorn hiretitan.api_main:create_app --factory``.

Builds the FastAPI app: the ``/api/v1`` router, RFC 9457 problem+json errors, security
headers and the built SPA. There is no authentication: the app is single-user and
listens on localhost only (FR-036).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hiretitan.platform.config.settings import Settings, get_settings
from hiretitan.platform.runtime.api import create_events_router

API_PREFIX: Final = "/api/v1"
PROBLEM_JSON: Final = "application/problem+json"
DEFAULT_DIST: Final = Path(__file__).resolve().parents[3] / "frontend" / "dist"

CSP: Final = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)
SECURITY_HEADERS: Final = (
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
)


class SecurityHeadersMiddleware:
    """Adds the security headers to every HTTP response (pure ASGI, so SSE still streams)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *SECURITY_HEADERS]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def problem(
    status: int, detail: str, *, errors: list[dict[str, str]] | None = None
) -> JSONResponse:
    title = HTTPStatus(status).phrase
    body: dict[str, Any] = {
        "type": f"https://httpstatuses.io/{status}",
        "title": title,
        "status": status,
        "detail": detail,
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def _field_path(loc: Sequence[Any]) -> str:
    parts = [str(part) for part in loc if part not in ("body", "query", "path")]
    return ".".join(parts)


async def _validation_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"field": _field_path(error["loc"]), "message": str(error["msg"])}
        for error in jsonable_encoder(exc.errors())
    ]
    return problem(422, "Some fields are not valid.", errors=errors)


async def _http_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return problem(exc.status_code, detail)


def _add_spa(app: FastAPI, dist: Path) -> None:
    root = dist.resolve()
    index = root / "index.html"

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "No such API endpoint.")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


def create_app(
    settings: Settings | None = None,
    *,
    frontend_dist: Path | None = None,
    routers: Sequence[APIRouter] = (),
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="HireTitan", docs_url=None, redoc_url=None)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)

    api = APIRouter()

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    api.include_router(create_events_router(settings.database_url))
    for router in routers:
        api.include_router(router)
    app.include_router(api, prefix=API_PREFIX)

    dist = frontend_dist or settings.frontend_dist or DEFAULT_DIST
    if (dist / "index.html").is_file():
        _add_spa(app, dist)
    return app


def server_loop_factory() -> Callable[[], asyncio.AbstractEventLoop]:
    """psycopg's async mode can't run on Windows' default Proactor loop."""
    return asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop


def main() -> None:
    settings = get_settings()
    config = uvicorn.Config(
        create_app(settings), host=settings.host, port=settings.port, loop="none"
    )
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=server_loop_factory())


if __name__ == "__main__":
    main()
