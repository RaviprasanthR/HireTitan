"""Mikasa's composition root (002m research R3): joins ``hiretitan.assistant`` to the action
catalogue, the profile-claim check of 002k and the AI provider's state.

``assistant`` sees none of these modules (import contract 9); everything it needs arrives here
through the protocols in ``assistant.application.ports``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan import prompts as hiretitan_prompts
from hiretitan.actions.cards import describe
from hiretitan.actions.catalogue import Catalogue
from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import (
    ActionContext,
    ActionError,
    PrivateResult,
    ReadResult,
    model_facing,
)
from hiretitan.assistant.api.conversations import create_conversations_router
from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.api.refs import create_refs_router
from hiretitan.assistant.api.status import create_status_router
from hiretitan.assistant.api.turns import create_turns_router
from hiretitan.assistant.application.ports import AssistantStatus, CallContext, ToolOutcome
from hiretitan.assistant.application.turn import TurnDeps
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.drafts.domain.checks import TechTerms, check_text
from hiretitan.drafts.domain.facts import drafting_facts, years_of_experience
from hiretitan.drafts.domain.selection import allowed_names
from hiretitan.drafts_wiring import SqlProfileFacts
from hiretitan.platform.clock import SystemClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.factory import build_llm
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.openai_adapter import PROVIDER as OPENAI
from hiretitan.platform.llm.port import ToolSpec
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.provider_status import Publish

_TOKEN = re.compile(r"\[\[[^\]]*\]\]")


def _refs(value: Any) -> list[str]:
    """Every ``ref`` value in a result, in order, once each."""
    found: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            ref = item.get("ref")
            if isinstance(ref, str) and ref not in found:
                found.append(ref)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found


class CatalogAdapter:
    """``ActionCatalog`` over the real catalogue: parses and validates each call, runs it in its
    own transaction, and returns only the model-facing result (research R3, R5, R9)."""

    def __init__(self, catalogue: Catalogue, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._catalogue = catalogue
        self._sessions = sessions

    def tool_specs(self) -> list[ToolSpec]:
        return self._catalogue.tool_specs()

    async def call(self, name: str, arguments_json: str, ctx: CallContext) -> ToolOutcome:
        spec = self._catalogue.get(name)
        if spec is None:
            return ToolOutcome(
                kind="unknown", valid=False, problem=f"there is no tool named {name}"
            )
        try:
            args = spec.args.model_validate_json(arguments_json or "{}")
        except ValidationError as error:
            return ToolOutcome(kind=spec.kind, valid=False, problem=_short(error))
        if spec.kind != "read":
            # Changes arrive with US2 (T020 onwards): until then they are refused plainly.
            return ToolOutcome(
                kind=spec.kind,
                valid=True,
                payload={"error": "not_yet", "message": "I can't change things yet."},
            )
        try:
            async with self._sessions() as session:
                result = await spec.handler(ActionContext(session, ctx.now), args)
        except ValueError as error:  # a ref of the wrong kind, or not a ref at all
            return ToolOutcome(kind=spec.kind, valid=False, problem=str(error))
        if isinstance(result, ActionError):
            return ToolOutcome(
                kind=spec.kind,
                valid=True,
                payload={"error": result.reason, "message": result.message},
            )
        if not isinstance(result, ReadResult | PrivateResult):
            raise TypeError(f"{name} returned {type(result).__name__}")
        payload = model_facing(result)
        return ToolOutcome(kind=spec.kind, valid=True, payload=payload, refs=_refs(payload))


def _short(error: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
        for e in error.errors()[:5]
    ]
    return "; ".join(parts)


class ProfileClaims:
    """``ProfileClaimsChecker`` with 002k's deterministic checks (FR-018a, constitution II)."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        tech_terms: TechTerms,
        today: Callable[[], date],
    ) -> None:
        self._profiles = SqlProfileFacts(sessions)
        self._tech_terms = tech_terms
        self._today = today

    async def unbacked(self, text: str, context: str) -> list[str]:
        profile = await self._profiles.current()
        if profile is None:
            return []  # nothing to claim from; the prompt says so instead
        view = profile.view
        problems = check_text(
            _TOKEN.sub(" ", text),
            [],
            drafting_facts(view),
            tech_terms=self._tech_terms,
            allowed_names=allowed_names(view, "", ""),
            years=years_of_experience(view, self._today()),
            context=_TOKEN.sub(" ", context),
        )
        return [problem.message for problem in problems]


class StatusCheck:
    """Can Mikasa be used now (FR-024): a key, a provider that accepts it, a model with tools."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        provider: str,
        has_key: Callable[[], bool],
        catalog: ModelCatalog,
    ) -> None:
        self._sessions = sessions
        self._provider = provider
        self._has_key = has_key
        self._catalog = catalog

    async def __call__(self) -> AssistantStatus:
        if not self._catalog.supports(self._provider, "fast", "tools"):
            return AssistantStatus(False, "model_lacks_tools")
        if not self._has_key():
            return AssistantStatus(False, "key_missing")
        async with self._sessions() as session:
            row = await ProviderStatusRepo(session).get(self._provider)
        if row is not None and row.status == "rejected":
            return AssistantStatus(False, "key_rejected")
        if row is not None and row.status == "missing":
            return AssistantStatus(False, "key_missing")
        if row is not None and row.status == "out_of_credit":
            return AssistantStatus(False, "out_of_credit", row.message)
        return AssistantStatus(True)


def fake_has_key(fake: FakeLlm) -> Callable[[], bool]:
    return lambda: fake.key_status() != "missing"


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def assistant_routers(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    publish: Publish,
    tech_terms: TechTerms,
) -> list[APIRouter]:
    """Mikasa's routers for the API process. Her turns run here, not on the worker (R2)."""
    built = build_llm(settings, sessions, publish)
    if built.chat is None:
        raise RuntimeError("The AI adapter has no chat side")
    clock = SystemClock()
    provider = "fake" if settings.llm == "fake" else OPENAI
    if built.fake is not None:
        has_key = fake_has_key(built.fake)
    elif built.keys is not None:
        has_key = built.keys.has_key
    else:
        has_key = lambda: False  # noqa: E731
    turn = TurnDeps(
        llm=built.chat,
        catalog=CatalogAdapter(build_catalogue(), sessions),
        store=SqlTurnStore(sessions),
        claims=ProfileClaims(sessions, tech_terms, lambda: clock.now().date()),
        prompt=PromptRegistry(Path(hiretitan_prompts.__file__).parent).load("mikasa_chat"),
        now=clock.now,
    )

    async def describe_ref(text: str) -> dict[str, Any] | None:
        async with sessions() as session:
            card = await describe(session, text)
        return asdict(card) if card is not None else None

    deps = AssistantApiDeps(
        sessions=sessions,
        turn=turn,
        describe=describe_ref,
        status=StatusCheck(
            sessions, provider=provider, has_key=has_key, catalog=ModelCatalog.load()
        ),
        now=clock.now,
    )
    return [
        create_status_router(deps),
        create_conversations_router(deps),
        create_turns_router(deps),
        create_refs_router(deps),
    ]
