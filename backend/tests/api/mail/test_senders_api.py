"""The sender list over the API (T036): US4 AS1-AS3, contracts/rest-api.md, Senders."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.mail.api.senders import MailSendersApiDeps, create_senders_router
from hiretitan.mail_wiring import seed_mail_senders
from hiretitan.platform.config.settings import Settings

SEED = Path(__file__).resolve().parents[3] / "seed" / "mail_senders.yaml"
SITES = {"linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort"}


@dataclass
class Env:
    client: httpx.AsyncClient


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    await seed_mail_senders(sessions, SEED)
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[create_senders_router(MailSendersApiDeps(sessions=sessions))],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client)


async def listed(env: Env) -> list[dict[str, object]]:
    return (await env.client.get("/api/v1/mail/senders")).json()["items"]  # type: ignore[no-any-return]


async def test_US4_AS1_builtin_listed_all_on(env: Env) -> None:
    items = await listed(env)

    assert {i["site"] for i in items} == SITES
    assert all(i["built_in"] is True and i["enabled"] is True for i in items)
    assert set(items[0]) == {"id", "address", "site", "built_in", "enabled"}
    sites = [i["site"] for i in items]
    assert sites == sorted(sites)  # by site


async def test_US4_AS2_add_sender_201(env: Env) -> None:
    response = await env.client.post(
        "/api/v1/mail/senders", json={"address": "  Digest@Board.Example "}
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["address"], body["site"], body["built_in"], body["enabled"]) == (
        "digest@board.example",
        "other",
        False,
        True,
    )
    assert (await listed(env))[-1]["address"] == "digest@board.example"  # built-in first


async def test_add_invalid_address_422(env: Env) -> None:
    response = await env.client.post("/api/v1/mail/senders", json={"address": "not an address"})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "address", "message": "'not an address' is not a plain email address."}
    ]
    assert all(i["built_in"] for i in await listed(env))  # nothing was added


@pytest.mark.parametrize(
    "address",
    [
        "a@b.co OR from:x@y.co",  # would widen the Gmail query
        'a"b@x.com',
        "-a@b.co",
        "a b@x.com",
        "a@b..com",
        f"{'a' * 320}@x.com",
        "",
    ],
)
async def test_hostile_address_is_refused(env: Env, address: str) -> None:
    response = await env.client.post("/api/v1/mail/senders", json={"address": address})

    assert response.status_code == 422
    assert all(i["built_in"] for i in await listed(env))


async def test_long_address_is_not_echoed_back(env: Env) -> None:
    response = await env.client.post("/api/v1/mail/senders", json={"address": "x" * 900})

    assert response.status_code == 422
    assert len(response.text) < 1500


async def test_missing_or_extra_field_422(env: Env) -> None:
    assert (await env.client.post("/api/v1/mail/senders", json={})).status_code == 422
    extra = {"address": "digest@board.example", "site": "linkedin"}
    assert (await env.client.post("/api/v1/mail/senders", json=extra)).status_code == 422


async def test_add_duplicate_409(env: Env) -> None:
    await env.client.post("/api/v1/mail/senders", json={"address": "digest@board.example"})

    again = await env.client.post("/api/v1/mail/senders", json={"address": "DIGEST@board.example"})
    built_in = await env.client.post(
        "/api/v1/mail/senders", json={"address": str((await listed(env))[0]["address"])}
    )

    assert (again.status_code, again.json()["reason"]) == (409, "sender_exists")
    assert (built_in.status_code, built_in.json()["reason"]) == (409, "sender_exists")


async def test_US4_AS3_switch_off(env: Env) -> None:
    first = (await listed(env))[0]

    off = await env.client.patch(f"/api/v1/mail/senders/{first['id']}", json={"enabled": False})
    on = await env.client.patch(f"/api/v1/mail/senders/{first['id']}", json={"enabled": True})

    assert (off.status_code, off.json()["enabled"]) == (200, False)
    assert (on.status_code, on.json()["enabled"]) == (200, True)
    assert (await listed(env))[0]["enabled"] is True


async def test_patch_cannot_change_site_or_address(env: Env) -> None:
    first = (await listed(env))[0]

    response = await env.client.patch(
        f"/api/v1/mail/senders/{first['id']}", json={"enabled": False, "site": "other"}
    )

    assert response.status_code == 422
    assert first == (await listed(env))[0]


async def test_patch_unknown_404(env: Env) -> None:
    response = await env.client.patch(f"/api/v1/mail/senders/{uuid4()}", json={"enabled": False})

    assert response.status_code == 404


async def test_delete_builtin_409(env: Env) -> None:
    first = (await listed(env))[0]

    response = await env.client.delete(f"/api/v1/mail/senders/{first['id']}")

    assert (response.status_code, response.json()["reason"]) == (409, "built_in")
    assert first in await listed(env)  # still there, unchanged


async def test_delete_added_204(env: Env) -> None:
    added = (
        await env.client.post("/api/v1/mail/senders", json={"address": "digest@board.example"})
    ).json()

    response = await env.client.delete(f"/api/v1/mail/senders/{added['id']}")

    assert response.status_code == 204
    assert added["id"] not in {i["id"] for i in await listed(env)}
    assert (await env.client.delete(f"/api/v1/mail/senders/{added['id']}")).status_code == 404
