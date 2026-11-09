"""T014: contacts and the company note (contracts/rest-api.md "Contacts and notes"; US2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.contacts import SearchContactsApiDeps, create_contacts_router
from hiretitan.search.infra.repos import CompaniesRepo

BASE = "/api/v1/companies"


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    company: UUID


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    async with sessions() as session:
        row = await CompaniesRepo(session).add(
            name="Example Co", origin="user", resolution="unresolved"
        )
        await session.commit()
        company = row.id
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[create_contacts_router(SearchContactsApiDeps(sessions=sessions))],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, company)


def url(env: Env, tail: str = "contacts") -> str:
    return f"{BASE}/{env.company}/{tail}"


async def add(env: Env, **body: object) -> httpx.Response:
    return await env.client.post(url(env), json=body)


async def test_US2_AS2_contact_with_only_a_name(env: Env) -> None:
    response = await add(env, name="Jane Example")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Jane Example"
    assert body["source"] == "typed"
    assert body["role"] is None
    assert body["linkedin_url"] is None
    assert {"id", "company_id", "email", "phone", "confidence", "note", "updated_at"} <= set(body)


async def test_US2_AS1_a_contact_with_every_field(env: Env) -> None:
    response = await add(
        env,
        name="Jane Example",
        role="Recruiter",
        linkedin_url="linkedin.com/in/jane-example",
        email="jane@example.com",
        phone="+91 98765 43210",
        confidence="high",
        note="Replies fast.",
    )

    assert response.status_code == 201
    assert response.json()["linkedin_url"] == "https://linkedin.com/in/jane-example"
    panel = (await env.client.get(url(env))).json()
    assert [c["name"] for c in panel["items"]] == ["Jane Example"]
    assert panel["note"] is None


async def test_US2_AS3_edit_and_delete_persist(env: Env) -> None:
    created = (await add(env, name="Jane Example", role="Recruiter")).json()
    contact_url = url(env, f"contacts/{created['id']}")

    edited = await env.client.patch(
        contact_url, json={"role": "Talent Lead", "email": "j@example.com"}
    )

    assert edited.status_code == 200
    assert edited.json()["role"] == "Talent Lead"
    assert edited.json()["name"] == "Jane Example"  # fields not sent do not change
    again = (await env.client.get(url(env))).json()["items"][0]
    assert (again["role"], again["email"]) == ("Talent Lead", "j@example.com")

    cleared = await env.client.patch(contact_url, json={"role": ""})
    assert cleared.json()["role"] is None  # an empty text clears an optional field

    deleted = await env.client.delete(contact_url)
    assert deleted.status_code == 204
    assert (await env.client.get(url(env))).json()["items"] == []


async def test_US2_AS6_bad_link_is_refused(env: Env) -> None:
    response = await add(env, name="Jane", linkedin_url="javascript:alert(1)")

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["linkedin_url"]
    assert (await env.client.get(url(env))).json()["items"] == []


async def test_FR012_bad_email_and_phone_refused(env: Env) -> None:
    response = await add(env, name="Jane", email="nope", phone="12")

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["email", "phone"]


async def test_FR009_a_contact_needs_a_name(env: Env) -> None:
    response = await add(env, role="Recruiter")

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["name"]


async def test_FR006_typed_duplicate_name_is_409_contact_exists(env: Env) -> None:
    await add(env, name="Jane Example")

    response = await add(env, name="  jane   EXAMPLE ")

    assert response.status_code == 409
    assert response.json()["code"] == "contact_exists"
    assert len((await env.client.get(url(env))).json()["items"]) == 1


async def test_rename_into_existing_name_is_409(env: Env) -> None:
    await add(env, name="Jane Example")
    other = (await add(env, name="John Sample")).json()

    response = await env.client.patch(
        url(env, f"contacts/{other['id']}"), json={"name": "Jane Example"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "contact_exists"


async def test_rename_to_a_new_name_and_to_the_same_name_in_other_case(env: Env) -> None:
    created = (await add(env, name="Jane Example")).json()
    contact_url = url(env, f"contacts/{created['id']}")

    same = await env.client.patch(contact_url, json={"name": "JANE EXAMPLE"})
    renamed = await env.client.patch(contact_url, json={"name": "Jane Q Example"})

    assert same.status_code == 200
    assert renamed.json()["name"] == "Jane Q Example"


async def test_FR010_note_set_and_clear(env: Env) -> None:
    saved = await env.client.put(url(env, "note"), json={"body": "Spoke to HR on Monday."})

    assert saved.status_code == 200
    assert saved.json()["body"] == "Spoke to HR on Monday."
    assert saved.json()["source"] == "typed"
    assert (await env.client.get(url(env))).json()["note"]["body"] == "Spoke to HR on Monday."

    cleared = await env.client.put(url(env, "note"), json={"body": "   "})

    assert cleared.status_code == 200
    assert cleared.json()["body"] is None
    assert (await env.client.get(url(env))).json()["note"] is None


async def test_FR010_note_over_5000_is_422(env: Env) -> None:
    response = await env.client.put(url(env, "note"), json={"body": "n" * 5001})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["body"]


async def test_unknown_company_is_404(env: Env) -> None:
    missing = f"{BASE}/{uuid4()}"

    assert (await env.client.get(f"{missing}/contacts")).status_code == 404
    assert (await env.client.post(f"{missing}/contacts", json={"name": "Jane"})).status_code == 404
    assert (await env.client.put(f"{missing}/note", json={"body": "x"})).status_code == 404


async def test_unknown_contact_is_404_and_another_companys_contact_is_not_reachable(
    env: Env,
) -> None:
    created = (await add(env, name="Jane Example")).json()
    async with env.sessions() as session:
        other = await CompaniesRepo(session).add(
            name="Other Co", origin="user", resolution="unresolved"
        )
        await session.commit()
        other_id = other.id

    wrong_company = f"{BASE}/{other_id}/contacts/{created['id']}"
    assert (await env.client.patch(wrong_company, json={"role": "x"})).status_code == 404
    assert (await env.client.delete(wrong_company)).status_code == 404
    unknown = url(env, f"contacts/{uuid4()}")
    assert (await env.client.delete(unknown)).status_code == 404


async def test_US2_AS5_job_company_panel_data(env: Env) -> None:
    await add(env, name="Jane Example", role="Recruiter")
    await add(env, name="John Sample")
    await env.client.put(url(env, "note"), json={"body": "Prefers email."})

    panel = (await env.client.get(url(env))).json()  # one call gives the panel everything

    assert [c["name"] for c in panel["items"]] == ["Jane Example", "John Sample"]
    assert panel["note"]["body"] == "Prefers email."


async def test_control_characters_are_stripped_from_typed_text(env: Env) -> None:
    response = await add(env, name="Ja\u0000ne Example", note="a\u0007b")

    assert response.json()["name"] == "Jane Example"
    assert response.json()["note"] == "ab"
