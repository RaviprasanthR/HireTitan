"""Only HireTitan's own page may change anything (002c final review, cross-site requests).

HireTitan has no login. A web page the person visits can still send a "simple" request to
``localhost:8000`` from the browser without asking first, for example a POST whose body has no
content type, which FastAPI reads as JSON. ``TrustedHostMiddleware`` does not stop it (the Host is
the app's own). So a request that changes something is refused when the browser says it comes
from another site (``Origin`` or ``Sec-Fetch-Site``). Reads, and requests with neither header
(scripts, tests, the CLI tools), are not affected.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings

BASE = "http://127.0.0.1:8000"


def client(tmp_path: Path, calls: list[str]) -> httpx.AsyncClient:
    router = APIRouter()

    @router.post("/wipe")
    async def wipe(body: dict[str, str]) -> dict[str, str]:
        calls.append(body.get("confirm", ""))
        return {"ok": "yes"}

    @router.get("/read")
    async def read() -> dict[str, str]:
        return {"ok": "yes"}

    app = create_app(Settings(), frontend_dist=tmp_path / "none", routers=[router])
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://evil.example"},
        {"Origin": "http://localhost:3000"},  # another program on this computer
        {"Origin": "null"},  # a sandboxed frame or a file
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
async def test_a_change_from_another_site_is_refused(
    tmp_path: Path, headers: dict[str, str]
) -> None:
    calls: list[str] = []
    async with client(tmp_path, calls) as http:
        # the browser's "simple" request: no content type, so no preflight, yet read as JSON
        response = await http.post(
            "/api/v1/wipe", content=b'{"confirm": "DELETE"}', headers=headers
        )

    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": BASE, "Sec-Fetch-Site": "same-origin"},
        {"Origin": BASE},
        {"Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "none"},  # typed into the address bar
        {},  # no browser: tests, scripts
    ],
)
async def test_the_apps_own_page_and_scripts_still_work(
    tmp_path: Path, headers: dict[str, str]
) -> None:
    calls: list[str] = []
    async with client(tmp_path, calls) as http:
        response = await http.post("/api/v1/wipe", json={"confirm": "DELETE"}, headers=headers)

    assert response.status_code == 200
    assert calls == ["DELETE"]


async def test_reads_from_another_site_are_left_to_the_browser(tmp_path: Path) -> None:
    # a GET changes nothing (Google's sign-in comes back to the callback as a cross-site GET)
    async with client(tmp_path, []) as http:
        response = await http.get(
            "/api/v1/read",
            headers={"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"},
        )

    assert response.status_code == 200
