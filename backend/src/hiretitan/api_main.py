"""API composition root: ``uvicorn hiretitan.api_main:create_app --factory``.

Builds the FastAPI app: the ``/api/v1`` router, RFC 9457 problem+json errors, security
headers and the built SPA. There is no authentication: the app is single-user and
listens on localhost only (FR-036).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Lifespan, Message, Receive, Scope, Send

from hiretitan.platform.clock import SystemClock
from hiretitan.platform.config.settings import Settings, get_settings
from hiretitan.platform.db import create_engine, session_factory
from hiretitan.platform.runtime.api import create_events_router, create_runs_router
from hiretitan.platform.runtime.procrastinate import CHECK_PROVIDER_KEY_TASK, create_runtime
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.platform.web.limits import BodyLimitMiddleware
from hiretitan.platform.web.problems import ProblemError, problem
from hiretitan.preferences.api.router import PreferencesApiDeps, create_preferences_router
from hiretitan.profile.api.profile import create_profile_router
from hiretitan.profile.api.resumes import ProfileApiDeps, create_resumes_router
from hiretitan.profile.api.reviews import create_reviews_router
from hiretitan.profile.infra.parsing.sniff import MAX_BYTES
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.api.rules import SearchRulesApiDeps, create_search_rules_router
from hiretitan.search.application.synonyms_seed import load_title_synonyms
from hiretitan.search_wiring import ProfileAndPreferencesSource
from hiretitan.setup.api.data import DataApiDeps, create_data_router
from hiretitan.setup.api.onboarding import OnboardingApiDeps, create_onboarding_router
from hiretitan.setup.api.review_items import ReviewItemsApiDeps, create_review_items_router
from hiretitan.setup.api.settings import SettingsApiDeps, create_settings_router
from hiretitan.setup.api.status import StatusApiDeps, create_status_router
from hiretitan.setup_wiring import RepoFacts, SqlDeleteAllStore

API_PREFIX: Final = "/api/v1"
MULTIPART_OVERHEAD: Final = 64 * 1024  # boundaries and headers around the file
DEFAULT_DIST: Final = Path(__file__).resolve().parents[3] / "frontend" / "dist"
SEED_DIR: Final = Path(__file__).resolve().parents[2] / "seed"

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


async def _problem_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, ProblemError)
    return problem(exc.status, exc.detail, extra=exc.extra)


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
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="HireTitan", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(
        BodyLimitMiddleware, path=f"{API_PREFIX}/resumes", limit=MAX_BYTES + MULTIPART_OVERHEAD
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(ProblemError, _problem_handler)

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


def build_app(settings: Settings | None = None) -> FastAPI:
    """The real application: database, file storage and job queue wired to the routers."""
    settings = settings or get_settings()
    engine = create_engine(settings.database_url)
    runtime = create_runtime(settings.database_url)
    deps = ProfileApiDeps(
        sessions=session_factory(engine),
        storage=LocalFileStorage(settings.data_dir),
        queue=runtime.queue,
    )

    provider = "fake" if settings.llm == "fake" else "openai"
    clock = SystemClock()

    async def enqueue_key_check() -> None:
        await runtime.app.configure_task(CHECK_PROVIDER_KEY_TASK).defer_async()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with runtime.app.open_async():  # the job queue connection, to defer jobs
            yield
        await engine.dispose()

    routers = [
        create_resumes_router(deps),
        create_reviews_router(deps),
        create_profile_router(deps),
        create_preferences_router(
            PreferencesApiDeps(
                sessions=deps.sessions, clock=SystemClock(), profile_reader=VersionsRepo
            )
        ),
        create_search_rules_router(
            SearchRulesApiDeps(
                sessions=deps.sessions,
                source=ProfileAndPreferencesSource,
                synonyms=load_title_synonyms(SEED_DIR / "title_synonyms.yaml"),
            )
        ),
        create_runs_router(deps.sessions, deps.queue),
        create_settings_router(
            SettingsApiDeps(
                sessions=deps.sessions, queue=deps.queue, clock=clock, provider=provider
            )
        ),
        create_status_router(
            StatusApiDeps(
                sessions=deps.sessions,
                clock=clock,
                provider=provider,
                facts=RepoFacts,
                enqueue_key_check=enqueue_key_check,
            )
        ),
        create_onboarding_router(
            OnboardingApiDeps(sessions=deps.sessions, clock=clock, facts=RepoFacts)
        ),
        create_review_items_router(ReviewItemsApiDeps(sessions=deps.sessions, facts=RepoFacts)),
        create_data_router(
            DataApiDeps(
                sessions=deps.sessions,
                storage=deps.storage,
                store=SqlDeleteAllStore,
                enqueue_key_check=enqueue_key_check,
            )
        ),
    ]
    return create_app(settings, routers=routers, lifespan=lifespan)


def main() -> None:
    settings = get_settings()
    config = uvicorn.Config(
        build_app(settings), host=settings.host, port=settings.port, loop="none"
    )
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=server_loop_factory())


if __name__ == "__main__":
    main()
