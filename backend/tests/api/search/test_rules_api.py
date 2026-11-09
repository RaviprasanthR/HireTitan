"""T020: the search rules endpoints (contracts/rest-api.md, "Search rules")."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.preferences.domain.model import Place, Preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.api.rules import SearchRulesApiDeps, create_search_rules_router
from hiretitan.search.application.synonyms_seed import load_title_synonyms
from hiretitan.search_wiring import ProfileAndPreferencesSource

SEED = Path(__file__).resolve().parents[3] / "seed" / "title_synonyms.yaml"
RULES = "/api/v1/search/rules"


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    deps = SearchRulesApiDeps(
        sessions=sessions,
        source=ProfileAndPreferencesSource,
        synonyms=load_title_synonyms(SEED),
    )
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_search_rules_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def confirm_profile(
    sessions: async_sessionmaker[AsyncSession], skills: tuple[str, ...]
) -> None:
    async with sessions() as session:
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane Example"), skills=skills),
            created_by="manual",
        )
        await session.commit()


async def save_preferences(
    sessions: async_sessionmaker[AsyncSession],
    *,
    roles: tuple[str, ...] = ("Backend Engineer",),
    saved_at: datetime = datetime(2026, 11, 5, tzinfo=UTC),
) -> None:
    prefs = Preferences(
        target_roles=roles,
        key_skills=("Python",),
        preferred_locations=(Place("Bengaluru", "IN"),),
        blocked_locations=(Place("Pune", "IN"),),
        work_modes=frozenset({"remote"}),
    )
    async with sessions() as session:
        await PreferencesRepo(session).write(prefs, saved_at)
        await session.commit()


async def ready(sessions: async_sessionmaker[AsyncSession]) -> None:
    await confirm_profile(sessions, ("Python", "Postgres"))
    await save_preferences(sessions)


def with_changes(rules: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {**rules, **changes}


async def test_empty_state(client: httpx.AsyncClient) -> None:
    got = (await client.get(RULES)).json()
    assert got == {"approved": None, "proposal": None, "stale": False}


async def test_US2_AS1_proposal_endpoint_returns_origins(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)

    response = await client.post(f"{RULES}/proposal")

    assert response.status_code == 201
    rule_set = response.json()
    assert rule_set["status"] == "proposed"
    words = rule_set["rules"]["title_words"]
    assert words[0] == {
        "text": "Backend Engineer",
        "origin": "preference:target_roles[0]",
        "effect": "skips",
    }
    assert any(w["origin"] == "synonym_table" for w in words)
    keywords = rule_set["rules"]["stack_keywords"]
    assert {k["effect"] for k in keywords} == {"guides_ai"}
    assert rule_set["rules"]["blocked_locations"][0]["effect"] == "skips"
    assert rule_set["based_on"]["profile_version_id"]


async def test_US2_AS2_edit_and_approve(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    proposal = (await client.post(f"{RULES}/proposal")).json()
    rules = proposal["rules"]

    edited = with_changes(
        rules,
        title_avoid=[{"text": "manager", "origin": "user"}],
        max_age_days=14,
    )
    put = await client.put(f"{RULES}/proposal", json=edited)
    assert put.status_code == 200

    approved = await client.post(f"{RULES}/proposal/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    got = (await client.get(RULES)).json()
    assert got["proposal"] is None
    assert got["approved"]["rules"]["max_age_days"] == 14
    assert got["approved"]["rules"]["title_avoid"][0]["text"] == "manager"
    assert got["stale"] is False


async def test_FR002_limits_return_field_errors(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    rules = (await client.post(f"{RULES}/proposal")).json()["rules"]

    response = await client.put(
        f"{RULES}/proposal", json=with_changes(rules, title_words=[], max_age_days=0)
    )

    assert response.status_code == 422
    assert {e["field"] for e in response.json()["errors"]} == {"title_words", "max_age_days"}


async def test_unknown_origin_or_effect_is_not_trusted(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    rules = (await client.post(f"{RULES}/proposal")).json()["rules"]
    rules["stack_keywords"] = [{"text": "Go", "origin": "made up"}]

    response = await client.put(f"{RULES}/proposal", json=rules)

    assert response.status_code == 422


@pytest.mark.parametrize("missing", ["profile", "preferences"])
async def test_proposal_409_without_profile(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession], missing: str
) -> None:
    if missing == "profile":
        await save_preferences(sessions)
        reason = "no_confirmed_profile"
    else:
        await confirm_profile(sessions, ("Python",))
        reason = "no_preferences"

    response = await client.post(f"{RULES}/proposal")

    assert response.status_code == 409
    assert response.json()["reason"] == reason


async def test_edit_and_approve_without_a_proposal_409(client: httpx.AsyncClient) -> None:
    approve = await client.post(f"{RULES}/proposal/approve")
    assert approve.status_code == 409
    assert approve.json()["reason"] == "no_proposal"


async def test_US2_AS4_discard_keeps_approved_and_new_proposal_does_not_replace_it(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    await client.post(f"{RULES}/proposal")
    approved = (await client.post(f"{RULES}/proposal/approve")).json()

    await client.post(f"{RULES}/proposal")
    assert (await client.delete(f"{RULES}/proposal")).status_code == 204

    got = (await client.get(RULES)).json()
    assert got["proposal"] is None
    assert got["approved"]["id"] == approved["id"]


async def test_FR006_changed_preferences_make_approved_rules_stale(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    await client.post(f"{RULES}/proposal")
    await client.post(f"{RULES}/proposal/approve")

    await save_preferences(
        sessions, roles=("Data Engineer",), saved_at=datetime(2026, 11, 6, tzinfo=UTC)
    )

    got = (await client.get(RULES)).json()
    assert got["stale"] is True
