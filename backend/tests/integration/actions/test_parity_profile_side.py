"""002m T027: Mikasa's risky changes to preferences, search rules and the display name go through
a confirm card and the same use cases as the pages (FR-006); none writes profile facts (FR-018).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.mail_env import make_run

from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionServices
from hiretitan.assistant.application.cards import confirm_card
from hiretitan.assistant.application.ports import ApplyOutcome, CallContext, ToolOutcome
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, card_units
from hiretitan.preferences.application.service import get_preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.search.application.rules import RulesService
from hiretitan.search.infra.repos import RuleSetsRepo
from hiretitan.search_wiring import ProfileAndPreferencesSource
from hiretitan.setup.infra.settings_repo import SettingsRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)


def rules_service(session: AsyncSession) -> RulesService:
    return RulesService(RuleSetsRepo(session), ProfileAndPreferencesSource(session), {})


@dataclass
class World:
    sessions: async_sessionmaker[AsyncSession]
    services: ActionServices
    conversation: UUID
    message: UUID

    async def propose(self, action: str, **args: Any) -> ToolOutcome:
        adapter = CatalogAdapter(build_catalogue(), self.sessions, self.services)
        return await adapter.call(
            action,
            json.dumps(args, default=str),
            CallContext(self.conversation, NOW, message_id=self.message),
        )

    async def run(self, action: str, **args: Any) -> ApplyOutcome:
        outcome = await self.propose(action, **args)
        assert outcome.card is not None, outcome.payload
        units = card_units(build_catalogue(), self.sessions, lambda: NOW, self.services)
        return await confirm_card(units, outcome.card.card_id, {}, NOW)


@pytest.fixture
async def world(sessions: async_sessionmaker[AsyncSession]) -> World:
    async with sessions() as session:
        conversation = await ConversationsRepo(session).create(now=NOW)
        message = await MessagesRepo(session).append(
            conversation.id, author="person", text="change it", now=NOW
        )
        await session.commit()
    return World(sessions, ActionServices(rules_service=rules_service), conversation.id, message.id)


async def test_FR006_update_preferences_merges_named_fields(world: World) -> None:
    applied = await world.run(
        "update_preferences",
        changes={
            "target_roles": ["Backend Engineer"],
            "notice_period_days": 45,
            "work_modes": ["remote"],
        },
    )

    async with world.sessions() as session:
        stored = await get_preferences(PreferencesRepo(session))
    assert stored.saved_at == NOW
    assert stored.content.notice_period_days == 45
    assert [str(mode) for mode in stored.content.work_modes] == ["remote"]
    assert applied.results[0]["summary"] == (
        "Saved your preferences (notice_period_days, target_roles, work_modes)."
    )


async def test_FR006_rules_go_through_proposal_and_approval(world: World) -> None:
    async with world.sessions() as session:
        await make_run(session, mode="rules_only")  # leaves an approved rule set
        await session.commit()
        approved_before = await RuleSetsRepo(session).approved()
        assert approved_before is not None

    await world.run(
        "edit_rule_proposal",
        changes={"title_words": [{"text": "Backend Engineer"}], "max_age_days": 14},
    )

    async with world.sessions() as session:
        repo = RuleSetsRepo(session)
        approved, proposal = await repo.approved(), await repo.proposed()
        assert approved is not None
        assert approved.id == approved_before.id  # nothing changed for searches yet
        assert proposal is not None

    await world.run("approve_rule_proposal")
    async with world.sessions() as session:
        now_approved = await RuleSetsRepo(session).approved()
        assert now_approved is not None
        assert now_approved.id != approved_before.id


async def test_FR006_set_display_name(world: World) -> None:
    await world.run("set_display_name", display_name="Sam")

    async with world.sessions() as session:
        record = await SettingsRepo(session).read_onboarding()
        assert record.display_name == "Sam"


def test_FR018_no_action_writes_profile_facts() -> None:
    profile_endpoints = ("/profile", "/resumes", "/onboarding/complete")
    for spec in build_catalogue().specs():
        if spec.kind == "read":
            continue
        for mirrored in spec.mirrors:
            path = mirrored.split(" ", 1)[1]
            assert not path.startswith(profile_endpoints), (spec.name, mirrored)
