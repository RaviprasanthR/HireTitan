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
from hiretitan.search.application.tables_seed import load_work_areas
from hiretitan.search_wiring import ProfileAndPreferencesSource

SEED = Path(__file__).resolve().parents[3] / "seed" / "title_synonyms.yaml"
AREAS_SEED = Path(__file__).resolve().parents[3] / "seed" / "work_areas.yaml"
RULES = "/api/v1/search/rules"


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> AsyncIterator[httpx.AsyncClient]:
    deps = SearchRulesApiDeps(
        sessions=sessions,
        source=ProfileAndPreferencesSource,
        synonyms=load_title_synonyms(SEED),
        work_areas=load_work_areas(AREAS_SEED),
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


async def test_approve_records_person(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """002i: a rule set the person approves says so; a proposal has no approver."""
    await ready(sessions)
    proposal = (await client.post(f"{RULES}/proposal")).json()
    assert proposal["approved_by"] is None
    approved = (await client.post(f"{RULES}/proposal/approve")).json()
    assert approved["approved_by"] == "person"
    assert (await client.get(RULES)).json()["approved"]["approved_by"] == "person"


async def test_FR030_FR031_proposal_has_the_area_and_avoid_words(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)

    proposal = (await client.post(f"{RULES}/proposal")).json()

    assert proposal["rules"]["areas"] == ["back_end"]
    avoid = {i["text"] for i in proposal["rules"]["title_avoid"]}
    assert {"frontend", "front end", "android"} <= avoid


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


async def test_edit_approved_opens_a_draft_copied_from_the_approved_rules(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    proposal = (await client.post(f"{RULES}/proposal")).json()
    await client.put(
        f"{RULES}/proposal",
        json=with_changes(proposal["rules"], title_avoid=[{"text": "intern", "origin": "user"}]),
    )
    approved = (await client.post(f"{RULES}/proposal/approve")).json()
    # the profile moves on, so a fresh proposal would differ from what was approved
    await save_preferences(
        sessions, roles=("Data Engineer",), saved_at=datetime(2026, 11, 6, tzinfo=UTC)
    )

    draft = await client.post(f"{RULES}/proposal/from-approved")

    assert draft.status_code == 201
    body = draft.json()
    assert body["status"] == "proposed"
    assert body["rules"] == approved["rules"]
    assert body["based_on"] == approved["based_on"]
    got = (await client.get(RULES)).json()
    assert got["approved"]["id"] == approved["id"]
    assert got["proposal"]["id"] == body["id"]


async def test_edit_approved_without_approved_rules_409(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)

    draft = await client.post(f"{RULES}/proposal/from-approved")

    assert draft.status_code == 409
    assert draft.json()["reason"] == "rules_not_approved"


# --- 002i: suggested rules, and saving edited rules in one step ------------------------------


async def test_FR017_suggested_writes_nothing(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)

    response = await client.get(f"{RULES}/suggested")

    assert response.status_code == 200
    rules = response.json()
    assert rules["title_words"][0]["text"] == "Backend Engineer"
    assert rules["areas"] == ["back_end"]
    # nothing was stored: no proposal, nothing approved
    assert (await client.get(RULES)).json() == {"approved": None, "proposal": None, "stale": False}


async def test_FR017_suggested_needs_a_profile_and_preferences(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{RULES}/suggested")
    assert response.status_code == 409
    assert response.json()["reason"] == "no_confirmed_profile"


async def test_FR015_put_approved_saves_new_version(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    await client.post(f"{RULES}/proposal")
    first = (await client.post(f"{RULES}/proposal/approve")).json()
    edited = with_changes(first["rules"], max_age_days=14)

    saved = await client.put(f"{RULES}/approved", json=edited)

    assert saved.status_code == 200
    body = saved.json()
    assert (body["status"], body["version"], body["approved_by"]) == ("approved", 2, "person")
    assert body["rules"]["max_age_days"] == 14
    state = (await client.get(RULES)).json()
    assert state["approved"]["id"] == body["id"]  # these are the rules searches use now
    assert state["proposal"] is None


async def test_FR015_put_approved_discards_open_proposal(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    await client.post(f"{RULES}/proposal")
    approved = (await client.post(f"{RULES}/proposal/approve")).json()
    await client.post(f"{RULES}/proposal/from-approved")  # an open draft is lying around

    assert (await client.put(f"{RULES}/approved", json=approved["rules"])).status_code == 200

    assert (await client.get(RULES)).json()["proposal"] is None


async def test_FR015_put_approved_works_before_anything_was_approved(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    suggested = (await client.get(f"{RULES}/suggested")).json()

    saved = await client.put(f"{RULES}/approved", json=suggested)

    assert saved.status_code == 200
    assert saved.json()["approved_by"] == "person"


async def test_FR017_saving_the_rules_clears_the_stale_notice(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    await client.post(f"{RULES}/proposal")
    approved = (await client.post(f"{RULES}/proposal/approve")).json()
    await save_preferences(
        sessions, roles=("Data Engineer",), saved_at=datetime(2026, 11, 6, tzinfo=UTC)
    )
    assert (await client.get(RULES)).json()["stale"] is True

    await client.put(f"{RULES}/approved", json=approved["rules"])

    assert (await client.get(RULES)).json()["stale"] is False  # checked against what they are now


async def test_FR016_put_approved_rejects_invalid_rules(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await ready(sessions)
    await client.post(f"{RULES}/proposal")
    approved = (await client.post(f"{RULES}/proposal/approve")).json()

    bad = with_changes(approved["rules"], title_words=[], max_age_days=0, areas=["backend"])
    response = await client.put(f"{RULES}/approved", json=bad)

    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert {"title_words", "max_age_days", "areas"} <= fields
    state = (await client.get(RULES)).json()
    assert (state["approved"]["id"], state["approved"]["version"]) == (approved["id"], 1)
