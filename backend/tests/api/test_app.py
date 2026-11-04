"""T016: the API composition root (health, problem+json, CSP, SPA serving, no auth)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings


class Item(BaseModel):
    name: str = Field(min_length=1)
    age: int


def extra_router() -> APIRouter:
    router = APIRouter()

    @router.post("/items")
    async def create_item(item: Item) -> Item:
        return item

    @router.get("/conflict")
    async def conflict() -> None:
        raise HTTPException(409, "A review is already open")

    @router.get("/too-big")
    async def too_big() -> None:
        raise HTTPException(413, "File is larger than 10 MB")

    @router.get("/wrong-type")
    async def wrong_type() -> None:
        raise HTTPException(415, "Only PDF and DOCX files are supported")

    return router


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>HireTitan</title>")
    (root / "assets" / "app.js").write_text("console.log('app')")
    return root


@pytest.fixture
async def client(dist: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(), frontend_dist=dist, routers=[extra_router()])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_health_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_validation_error_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/items", json={"name": "", "age": "x"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    for key in ("title", "type", "detail"):
        assert body[key]
    fields = {error["field"] for error in body["errors"]}
    assert fields == {"name", "age"}
    assert all(error["message"] for error in body["errors"])


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/api/v1/conflict", 409),
        ("/api/v1/too-big", 413),
        ("/api/v1/wrong-type", 415),
        ("/api/v1/does-not-exist", 404),
    ],
)
async def test_http_errors_are_problem_json(
    client: httpx.AsyncClient, path: str, status: int
) -> None:
    response = await client.get(path)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"]


async def test_csp_header_present(client: httpx.AsyncClient) -> None:
    for path in ("/api/v1/health", "/", "/api/v1/does-not-exist"):
        headers = (await client.get(path)).headers
        csp = headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "unsafe-inline" not in csp.split("style-src")[0]  # no inline scripts
        assert "script-src" not in csp or "unsafe-inline" not in csp
        assert headers["x-content-type-options"] == "nosniff"


async def test_spa_fallback_serves_index(client: httpx.AsyncClient) -> None:
    for path in ("/", "/profile", "/profile/review/abc"):
        response = await client.get(path)
        assert response.status_code == 200
        assert "<title>HireTitan</title>" in response.text
    assert (await client.head("/profile")).status_code == 200
    asset = await client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text


async def test_spa_fallback_cannot_leave_the_dist_folder(
    client: httpx.AsyncClient, dist: Path
) -> None:
    (dist.parent / "secret.txt").write_text("secret")
    response = await client.get("/%2e%2e/secret.txt")
    assert "secret" not in response.text


async def test_api_paths_never_fall_back_to_index(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert "<title>" not in response.text


async def test_FR036_no_auth_required(client: httpx.AsyncClient, dist: Path) -> None:
    app = create_app(Settings(), frontend_dist=dist, routers=[extra_router()])
    middleware = [m.cls.__name__.lower() for m in app.user_middleware]
    assert not any("auth" in name or "session" in name for name in middleware)
    for path in ("/api/v1/health", "/", "/profile"):
        response = await client.get(path)
        assert response.status_code == 200
        assert "www-authenticate" not in response.headers
