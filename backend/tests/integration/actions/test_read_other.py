"""002m T010: Mikasa's other read actions: searches, mail, companies, profile, preferences, rules,
review items and settings (contracts/actions.md; FR-005, FR-018, FR-020, EC-12)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from tests.fakes.drafts_env import MY_EMAIL, MY_LINK, MY_NAME, MY_PHONE, synthetic_content
from tests.fakes.mail_env import make_run

from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionContext, ActionError, ReadResult, model_facing
from hiretitan.mail.infra.models import MailConnectionRow, MailSenderRow
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo, SearchRunsRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)


async def run(session: AsyncSession, action: str, **args: Any) -> Any:
    spec = build_catalogue().get(action)
    assert spec is not None, action
    assert spec.kind == "read"
    return await spec.handler(ActionContext(session, NOW), spec.args(**args))


def seen_by_model(result: Any) -> str:
    return json.dumps(model_facing(result), default=str)


async def test_FR005_read_actions_return_bounded_fields(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session, mode="rules_only")
    await SearchRunsRepo(db_session).get(run_id)

    latest = await run(db_session, "get_latest_search")
    history = await run(db_session, "list_search_runs")
    one = await run(db_session, "get_search_run", search_run=f"search_run:{run_id}")

    assert isinstance(latest, ReadResult)
    assert latest.items[0]["ref"] == f"search_run:{run_id}"
    assert {"jobs_found", "added", "kept", "running", "mode"} <= set(latest.items[0])
    assert [item["ref"] for item in history.items] == [f"search_run:{run_id}"]
    assert one.items[0]["ref"] == f"search_run:{run_id}"


async def test_FR005_no_search_yet(db_session: AsyncSession) -> None:
    latest = await run(db_session, "get_latest_search")
    assert latest.items == []
    assert latest.total == 0


async def test_FR005_companies_with_counts_but_no_private_text(db_session: AsyncSession) -> None:
    acme = await CompaniesRepo(db_session).add(name="Acme", origin="user", resolution="verified")
    await CompaniesRepo(db_session).add(name="Zoho", origin="user", resolution="verified")
    await ContactsRepo(db_session).add(
        acme.id,
        ContactFields(name="Quillon Fairweather", role="Talent Partner"),
        source="typed",
    )
    await NotesRepo(db_session).set(acme.id, "Private note distinctive-note-5521", source="typed")

    found = await run(db_session, "search_companies", name="acm")
    one = await run(db_session, "get_company", company=f"company:{acme.id}")

    assert [item["name"] for item in found.items] == ["Acme"]
    item = one.items[0]
    assert item["ref"] == f"company:{acme.id}"
    assert item["contact_count"] == 1
    assert item["has_note"] is True
    for result in (found, one):
        text = seen_by_model(result)
        assert "Quillon" not in text
        assert "distinctive-note-5521" not in text


async def test_FR018_profile_read_has_no_contact_details(db_session: AsyncSession) -> None:
    await VersionsRepo(db_session).create_version(synthetic_content(), created_by="manual")

    result = await run(db_session, "get_profile")

    text = seen_by_model(result)
    for private in (MY_NAME, MY_EMAIL, MY_PHONE, MY_LINK):
        assert private not in text
    profile = result.items[0]
    assert profile["skills"]
    assert profile["experience"][0]["employer"]


async def test_FR018_no_profile_yet(db_session: AsyncSession) -> None:
    result = await run(db_session, "get_profile")
    assert result == ActionError("no_profile", "There is no confirmed profile yet.")


async def test_FR005_preferences_rules_review_and_settings(db_session: AsyncSession) -> None:
    await make_run(db_session, mode="rules_only")  # approves a rule set too

    preferences = await run(db_session, "get_preferences")
    rules = await run(db_session, "get_search_rules")
    review = await run(db_session, "list_review_items")
    settings = await run(db_session, "get_settings")

    assert "saved" in preferences.items[0]
    assert rules.items[0]["approved"] is not None
    assert review.items == []
    assert {"ai_status", "checklist"} <= set(settings.items[0])
    assert "key" not in json.dumps(settings.items[0]["checklist"]).replace("key_ok", "")


async def test_FR020_mail_status_has_no_email_text(db_session: AsyncSession) -> None:
    db_session.add(
        MailConnectionRow(
            provider="gmail",
            address="person.private@example.invalid",
            state="connected",
            connected_at=NOW,
        )
    )
    db_session.add(
        MailSenderRow(
            address="alerts@naukri.example",
            site="naukri",
            purpose="job_alert",
            built_in=True,
            enabled=True,
        )
    )
    await db_session.flush()

    result = await run(db_session, "get_mail_status")

    status = result.items[0]
    assert status["connected"] is True
    assert status["senders"] == [{"site": "naukri", "built_in": True, "enabled": True}]
    assert "person.private@example.invalid" not in seen_by_model(result)


async def test_EC12_mail_actions_report_not_connected(db_session: AsyncSession) -> None:
    result = await run(db_session, "get_mail_status")

    status = result.items[0]
    assert status["connected"] is False
    assert status["state"] == "not_connected"
    assert status["page"] == "/settings/gmail"
