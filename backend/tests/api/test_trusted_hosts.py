"""Only this computer's own names may reach the API (002c US6 review, DNS rebinding).

HireTitan has no login; its port is published on localhost only. A web page the person visits
could still point a name of its own at 127.0.0.1 and talk to the API from the browser ("DNS
rebinding"). The ``Host`` header then names the page's site, so anything but a local name is
refused before a route runs.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings


def client(tmp_path: Path, base: str, **settings: object) -> httpx.AsyncClient:
    app = create_app(Settings(**settings), frontend_dist=tmp_path / "none")  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base)


@pytest.mark.parametrize(
    "base", ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000", "http://test"]
)
async def test_local_names_are_served(tmp_path: Path, base: str) -> None:
    async with client(tmp_path, base) as http:
        assert (await http.get("/api/v1/health")).status_code == 200


@pytest.mark.parametrize("base", ["http://evil.example:8000", "http://192.168.1.20:8000"])
async def test_any_other_name_is_refused(tmp_path: Path, base: str) -> None:
    async with client(tmp_path, base) as http:
        response = await http.get("/api/v1/health")
        put = await http.put("/api/v1/settings/ai-key", json={"key": "sk-test-0123456789abcdef"})

    assert response.status_code == 400
    assert put.status_code == 400


async def test_more_names_can_be_allowed_in_settings(tmp_path: Path) -> None:
    async with client(
        tmp_path, "http://hiretitan.lan:8000", allowed_hosts="127.0.0.1,localhost,hiretitan.lan"
    ) as http:
        assert (await http.get("/api/v1/health")).status_code == 200
