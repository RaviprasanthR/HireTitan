"""Mikasa's composition root (002m research R3): joins ``hiretitan.assistant`` to the action
catalogue, the profile-claim check of 002k and the AI provider's state.

``assistant`` sees none of these modules (import contract 9); everything it needs arrives here
through the protocols in ``assistant.application.ports``.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan import prompts as hiretitan_prompts
from hiretitan.actions.cards import describe
from hiretitan.actions.catalogue import Catalogue
from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import (
    ActionContext,
    ActionError,
    ActionRefusedError,
    ActionServices,
    ActionSpec,
    Applied,
    ChangeView,
    PrivateResult,
    ReadResult,
    model_facing,
)
from hiretitan.assistant.api.changes import create_changes_router
from hiretitan.assistant.api.conversations import create_conversations_router
from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.api.quick import create_quick_router
from hiretitan.assistant.api.refs import create_refs_router
from hiretitan.assistant.api.staged import create_staged_router
from hiretitan.assistant.api.status import create_status_router
from hiretitan.assistant.api.turns import create_turns_router
from hiretitan.assistant.application.ports import (
    ApplyOutcome,
    AssistantStatus,
    CallContext,
    CardNotice,
    CardRecord,
    CardUnit,
    CardUnitFactory,
    ChangeNotice,
    ChangeRecord,
    ToolOutcome,
    UndoUnit,
    UndoUnitFactory,
)
from hiretitan.assistant.application.turn import TurnDeps
from hiretitan.assistant.domain.fingerprints import fingerprint
from hiretitan.assistant.infra.models import CARD_ITEMS_MAX
from hiretitan.assistant.infra.repos import CardsRepo, ChangesRepo, MessagesRepo, NewChange
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.drafts.api.drafts import DraftIn, DraftsApiDeps, RecipientIn, start_draft
from hiretitan.drafts.api.resumes import start_tailor
from hiretitan.drafts.domain.checks import TechTerms, check_text
from hiretitan.drafts.domain.facts import drafting_facts, years_of_experience
from hiretitan.drafts.domain.recipient import HIRING_TEAM
from hiretitan.drafts.domain.selection import allowed_names
from hiretitan.drafts.infra.repos import TailoredRepo
from hiretitan.drafts_wiring import (
    SqlContacts,
    SqlJobs,
    SqlProfileFacts,
    clear_drafts_for_job,
)
from hiretitan.mail_wiring import SqlCheckRuns
from hiretitan.platform.clock import SystemClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.factory import build_llm
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.openai_adapter import PROVIDER as OPENAI
from hiretitan.platform.llm.port import (
    AiUnavailable,
    LlmPort,
    LlmRequest,
    RetryableLlmError,
    ToolSpec,
)
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.provider_status import Publish
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.application.paste import PasteError, PasteInput, paste_job
from hiretitan.search.application.rules import RulesService
from hiretitan.search.application.search import start_search
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.paste_store import SqlPasteStore
from hiretitan.search.infra.repos import RuleSetsRepo
from hiretitan.search.infra.search_store import SearchStore
from hiretitan.search_wiring import ProfileAndPreferencesSource, SetupFinishedGate
from hiretitan.staged_wiring import StagedFlowImpl

_TOKEN = re.compile(r"\[\[[^\]]*\]\]")
UNDO_WINDOW = timedelta(hours=24)


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

    def __init__(
        self,
        catalogue: Catalogue,
        sessions: async_sessionmaker[AsyncSession],
        services: ActionServices | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._sessions = sessions
        self._services = services or ActionServices()

    def _ctx(self, session: AsyncSession, now: datetime) -> ActionContext:
        return ActionContext(session, now, self._services)

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
        if spec.kind == "small":
            return await self._apply_small(spec, args, ctx)
        if spec.kind == "risky":
            return await self._propose(spec, args, ctx)
        try:
            async with self._sessions() as session:
                result = await spec.handler(self._ctx(session, ctx.now), args)
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

    async def _apply_small(
        self, spec: ActionSpec, args: BaseModel, ctx: CallContext
    ) -> ToolOutcome:
        """Apply at once and record the change with its Undo, in one transaction (R6)."""
        if ctx.message_id is None:
            raise ValueError("A small change needs the person's message it answers")
        try:
            async with self._sessions() as session:
                result = await spec.handler(self._ctx(session, ctx.now), args)
                if isinstance(result, ActionError):
                    await session.rollback()
                    return ToolOutcome(
                        kind="small",
                        valid=True,
                        payload={"error": result.reason, "message": result.message},
                    )
                if not isinstance(result, Applied):
                    raise TypeError(f"{spec.name} returned {type(result).__name__}")
                until = ctx.now + UNDO_WINDOW
                record = await ChangesRepo(session).save(
                    NewChange(
                        conversation_id=ctx.conversation_id,
                        message_id=ctx.message_id,
                        action=spec.name,
                        target_kind=result.target_kind,
                        target_id=result.target_id,
                        before=result.before,
                        after=result.after,
                        created_rows=list(result.created_rows),
                        undoable_until=until,
                        summary=result.summary,
                    ),
                    now=ctx.now,
                )
                await session.commit()
        except ValueError as error:  # a ref of the wrong kind, or not a ref at all
            return ToolOutcome(kind="small", valid=False, problem=str(error))
        return ToolOutcome(
            kind="small",
            valid=True,
            payload={"done": result.summary, "change_id": str(record.id), "refs": result.refs},
            refs=list(result.refs),
            change=ChangeNotice(
                change_id=record.id,
                action=spec.name,
                summary=result.summary,
                undo_until=until,
                invalidate=[[key] for key in spec.invalidate],
            ),
        )

    async def _propose(self, spec: ActionSpec, args: BaseModel, ctx: CallContext) -> ToolOutcome:
        """A risky change waits on a card the person confirms (R7). HireTitan, not the model,
        writes what the card says; the targets are fingerprinted now and checked on confirm."""
        if ctx.message_id is None:
            raise ValueError("A card needs the person's message it answers")
        assert spec.targets is not None
        try:
            async with self._sessions() as session:
                targets = await spec.targets(self._ctx(session, ctx.now), args)
                if not targets:
                    return ToolOutcome(
                        kind="risky",
                        valid=True,
                        payload={"error": "not_found", "message": "There is nothing to change."},
                    )
                if len(targets) > CARD_ITEMS_MAX:
                    return ToolOutcome(
                        kind="risky",
                        valid=True,
                        payload={
                            "error": "bulk_limit",
                            "message": f"That is {len(targets)} items; I can do at most "
                            f"{CARD_ITEMS_MAX} at once. The page for it can do them all.",
                        },
                    )
                labels = [str(fields.get("label", key)) for key, fields in targets.items()]
                summary = _card_summary(spec.card_title or spec.name, labels)
                item = {
                    "action": spec.name,
                    "args": args.model_dump(mode="json"),
                    "editable": list(spec.editable),
                }
                card = await CardsRepo(session).create(
                    ctx.conversation_id,
                    ctx.message_id,
                    items=[item],
                    fingerprints={key: fingerprint(f) for key, f in targets.items()},
                    summary=summary,
                    now=ctx.now,
                )
                await session.commit()
        except ActionRefusedError as error:
            return ToolOutcome(
                kind="risky", valid=True, payload={"error": error.reason, "message": str(error)}
            )
        except ValueError as error:
            return ToolOutcome(kind="risky", valid=False, problem=str(error))
        return ToolOutcome(
            kind="risky",
            valid=True,
            payload={
                "waiting_for_confirmation": summary,
                "card_id": str(card.id),
                "note": "Nothing has changed yet: the person confirms or cancels the card.",
            },
            card=CardNotice(
                card_id=card.id, summary=summary, items=[item], expires_at=card.expires_at
            ),
        )


def _card_summary(title: str, labels: list[str]) -> str:
    shown = ", ".join(labels[:5])
    more = f" and {len(labels) - 5} more" if len(labels) > 5 else ""
    return f"{title}: {shown}{more}"[:2000]


class SqlCardUnit:
    """``CardUnit`` on one session: confirm applies every item here, or none (FR-012)."""

    def __init__(
        self,
        catalogue: Catalogue,
        session: AsyncSession,
        now: datetime,
        services: ActionServices | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._session = session
        self._ctx = ActionContext(session, now, services or ActionServices())

    async def card(self, card_id: UUID) -> CardRecord | None:
        row = await CardsRepo(self._session).get(card_id)
        if row is None:
            return None
        return CardRecord(
            id=row.id,
            conversation_id=row.conversation_id,
            state=row.state,
            items=list(row.items),
            fingerprints=dict(row.fingerprints),
            expires_at=row.expires_at,
        )

    def _spec(self, item: Mapping[str, Any]) -> ActionSpec | None:
        spec = self._catalogue.get(str(item.get("action")))
        return spec if spec is not None and spec.kind == "risky" else None

    async def problems(self, items: list[dict[str, Any]]) -> list[str]:
        found: list[str] = []
        for index, item in enumerate(items):
            spec = self._spec(item)
            if spec is None:
                found.append(f"Item {index + 1} is not something Mikasa can do.")
                continue
            try:
                spec.args.model_validate(item["args"])
            except ValidationError as error:
                found.append(f"Item {index + 1}: {_short(error)}")
        return found

    async def fingerprints(self, items: list[dict[str, Any]]) -> dict[str, str]:
        found: dict[str, str] = {}
        for item in items:
            spec = self._spec(item)
            if spec is None or spec.targets is None:
                continue
            targets = await spec.targets(self._ctx, spec.args.model_validate(item["args"]))
            found.update({key: fingerprint(fields) for key, fields in targets.items()})
        return found

    async def claim(self, card_id: UUID, now: datetime) -> bool:
        return await CardsRepo(self._session).claim_for_apply(card_id, now=now) is not None

    async def apply(
        self, card: CardRecord, items: list[dict[str, Any]], now: datetime
    ) -> ApplyOutcome:
        outcome = ApplyOutcome(ok=True)
        for item in items:
            spec = self._spec(item)
            if spec is None:
                return ApplyOutcome(ok=False, error="That is not something Mikasa can do.")
            result = await spec.handler(self._ctx, spec.args.model_validate(item["args"]))
            if isinstance(result, ActionError):
                return ApplyOutcome(ok=False, error=result.message)
            for applied in result if isinstance(result, list) else [result]:
                await self._record(card, spec, applied, now, outcome)
        return outcome

    async def _record(
        self, card: CardRecord, spec: ActionSpec, result: Any, now: datetime, outcome: ApplyOutcome
    ) -> None:
        """One change record per item changed, so a bulk card's items undo one by one."""
        if not isinstance(result, Applied):
            raise TypeError(f"{spec.name} returned {type(result).__name__}")
        record = await ChangesRepo(self._session).save(
            NewChange(
                conversation_id=card.conversation_id,
                card_id=card.id,
                action=spec.name,
                target_kind=result.target_kind,
                target_id=result.target_id,
                before=result.before,
                after=result.after,
                created_rows=list(result.created_rows),
                undoable_until=now + UNDO_WINDOW if spec.undo is not None else None,
                summary=result.summary,
            ),
            now=now,
        )
        outcome.results.append(
            {
                "action": spec.name,
                "summary": result.summary,
                "change_id": str(record.id),
                "undoable": spec.undo is not None,
                "refs": list(result.refs),
                "invalidate": [[key] for key in spec.invalidate],
            }
        )
        if result.after_commit is not None:
            outcome.after_commit.append(result.after_commit)

    async def set_state(
        self, card_id: UUID, state: str, now: datetime, result: list[Any] | None = None
    ) -> None:
        await CardsRepo(self._session).set_state(card_id, state, now=now, result=result)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


def card_units(
    catalogue: Catalogue,
    sessions: async_sessionmaker[AsyncSession],
    now: Callable[[], datetime],
    services: ActionServices | None = None,
) -> CardUnitFactory:
    @asynccontextmanager
    async def open_unit() -> AsyncIterator[CardUnit]:
        async with sessions() as session:
            yield SqlCardUnit(catalogue, session, now(), services)

    return open_unit


class SqlUndoUnit:
    """``UndoUnit`` on one session: the change row is locked when it is read (EC-03)."""

    def __init__(
        self,
        catalogue: Catalogue,
        session: AsyncSession,
        now: datetime,
        services: ActionServices | None = None,
    ) -> None:
        self._catalogue = catalogue
        self._session = session
        self._ctx = ActionContext(session, now, services or ActionServices())

    async def change(self, change_id: UUID) -> ChangeRecord | None:
        row = await ChangesRepo(self._session).get_for_update(change_id)
        if row is None:
            return None
        return ChangeRecord(
            id=row.id,
            action=row.action,
            target_kind=row.target_kind,
            target_id=row.target_id,
            before=dict(row.before),
            after=dict(row.after),
            created_rows=[str(r) for r in row.created_rows],
            undoable_until=row.undoable_until,
            undone_at=row.undone_at,
        )

    async def is_latest(self, change: ChangeRecord) -> bool:
        latest = await ChangesRepo(self._session).latest_for(change.target_kind, change.target_id)
        return latest is not None and latest.id == change.id

    async def current(self, change: ChangeRecord) -> Mapping[str, Any] | None:
        spec = self._catalogue.get(change.action)
        if spec is None or spec.current is None:
            return None
        return await spec.current(self._ctx, change.target_id)

    async def run_undo(self, change: ChangeRecord) -> None:
        spec = self._catalogue.get(change.action)
        if spec is None or spec.undo is None:
            raise LookupError(f"{change.action} has no undo")
        await spec.undo(
            self._ctx,
            ChangeView(
                target_kind=change.target_kind,
                target_id=change.target_id,
                before=change.before,
                after=change.after,
                created_rows=change.created_rows,
            ),
        )

    async def mark_undone(self, change_id: UUID, now: datetime) -> None:
        await ChangesRepo(self._session).mark_undone(change_id, now=now)

    async def commit(self) -> None:
        await self._session.commit()


def undo_units(
    catalogue: Catalogue,
    sessions: async_sessionmaker[AsyncSession],
    now: Callable[[], datetime],
    services: ActionServices | None = None,
) -> UndoUnitFactory:
    @asynccontextmanager
    async def open_unit() -> AsyncIterator[UndoUnit]:
        async with sessions() as session:
            yield SqlUndoUnit(catalogue, session, now(), services)

    return open_unit


class TopicChecker:
    """The tool-less topic check of a typed message (FR-030, research R17).

    One small call with a strict schema; the message goes in as delimited data. Any failure
    answers None, so the turn goes on and FR-031 still guards the reply."""

    def __init__(
        self,
        llm: LlmPort,
        prompts: PromptRegistry,
        sessions: async_sessionmaker[AsyncSession],
    ) -> None:
        self._llm = llm
        self._prompt = prompts.load("mikasa_topic")
        self._sessions = sessions

    async def __call__(self, text: str) -> bool | None:
        rendered = self._prompt.render()
        request = LlmRequest(
            task="mikasa_topic",
            prompt=rendered,
            output_schema=self._prompt.output_schema,
            tier=self._prompt.version.tier,
            max_output_tokens=self._prompt.version.max_output_tokens,
            untrusted_blocks=[delimit("message", sanitize(text).text)],
        )
        try:
            result = await self._llm.generate(request)
        except (AiUnavailable, RetryableLlmError):
            return None
        async with self._sessions() as session:
            await CallsRepo(session).record(
                LlmCallRecord(
                    task="mikasa_topic",
                    prompt_name=self._prompt.version.name,
                    prompt_version=str(self._prompt.version.version),
                    provider=result.provider,
                    model=result.model,
                    input_tokens=result.usage.input_tokens,
                    cached_input_tokens=result.usage.cached_input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.usage.latency_ms,
                    outcome=result.outcome,
                )
            )
            await session.commit()
        value = result.value
        return None if value is None else bool(value.on_topic)  # type: ignore[attr-defined]


def paste_into(
    sessions: async_sessionmaker[AsyncSession], now: Callable[[], datetime]
) -> Callable[[UUID, dict[str, Any]], Awaitable[dict[str, Any]]]:
    """The composer's Paste a job description (FR-021): the paste use case, a person message
    that says what happened (never the text), and a change with the same Undo as add_job."""

    async def paste(conversation_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
        at = now()
        async with sessions() as session:
            try:
                result = await paste_job(
                    SqlPasteStore(session),
                    PasteInput(
                        url=fields["url"],
                        description=fields["description"],
                        title=fields.get("title"),
                        company=fields.get("company"),
                        location=fields.get("location"),
                    ),
                    now=at,
                )
            except PasteError as error:
                return {"errors": [{"field": e.field, "message": e.message} for e in error.errors]}
            job = await session.get(JobRow, result.job_id)
            assert job is not None
            label = f"{job.title} at {job.company_name}"
            message = await MessagesRepo(session).append(
                conversation_id, author="person", text=f"Pasted a job description: {label}.", now=at
            )
            ref = f"job:{job.id}"
            if result.merged_into is not None:
                await session.commit()
                return {"summary": f"{label} was already here; the link was added.", "refs": [ref]}
            fields_now = {"state": job.state, "applied_on": None, "inquired_on": None, "extras": 0}
            record = await ChangesRepo(session).save(
                NewChange(
                    conversation_id=conversation_id,
                    message_id=message.id,
                    action="add_job",
                    target_kind="job",
                    target_id=job.id,
                    before={},
                    after=fields_now,
                    created_rows=[ref],
                    undoable_until=at + UNDO_WINDOW,
                    summary=f"Added {label}.",
                ),
                now=at,
            )
            await session.commit()
            return {
                "change_id": str(record.id),
                "summary": f"Added {label}.",
                "refs": [ref],
                "undo_until": (at + UNDO_WINDOW).isoformat(),
            }

    return paste


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
    services: ActionServices | None = None,
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
    catalogue = build_catalogue()

    async def changed(keys: list[list[str]]) -> None:
        await publish("assistant.changed", {"keys": keys})

    prompts = PromptRegistry(Path(hiretitan_prompts.__file__).parent)
    turn = TurnDeps(
        topic=TopicChecker(built.llm, prompts, sessions),
        llm=built.chat,
        catalog=CatalogAdapter(catalogue, sessions, services),
        publish=changed,
        store=SqlTurnStore(sessions),
        claims=ProfileClaims(sessions, tech_terms, lambda: clock.now().date()),
        prompt=prompts.load("mikasa_chat"),
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
        cards=card_units(catalogue, sessions, clock.now, services),
        undo=undo_units(catalogue, sessions, clock.now, services),
        paste=paste_into(sessions, clock.now),
        publish=changed,
        staged=StagedFlowImpl(
            sessions, built.llm, prompts, services.queue, provider, clock.now, changed
        )
        if services is not None and services.queue is not None
        else None,
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
        create_changes_router(deps),
        create_quick_router(deps),
        create_staged_router(deps),
    ]


def action_services(
    sessions: async_sessionmaker[AsyncSession],
    *,
    queue: Any,
    clock: Any,
    synonyms: Mapping[str, tuple[str, ...]],
    work_areas: Any,
    careers: Any,
    provider: str = "openai",
) -> ActionServices:
    """The services some actions need, made from the same objects the routes use (FR-006)."""

    def rules(session: AsyncSession) -> RulesService:
        return RulesService(
            RuleSetsRepo(session), ProfileAndPreferencesSource(session), synonyms, work_areas
        )

    async def start(session: AsyncSession, mode: str, now: datetime) -> UUID:
        started = await start_search(
            cast(Any, mode),
            rules=rules(session),
            setup=SetupFinishedGate(session),
            store=SearchStore(session),
            queue=queue,
            now=now,
        )
        return started.search_run_id

    async def check_mail(now: datetime, reread: bool) -> UUID:
        runs = SqlCheckRuns(sessions, lambda run_id: queue.enqueue(run_id))
        started = await runs.start(trigger="button", now=now, reread=reread)
        return started.search_run_id

    drafts = DraftsApiDeps(
        sessions=sessions,
        queue=queue,
        jobs=SqlJobs(sessions),
        profile=SqlProfileFacts(sessions),
        contacts=SqlContacts(sessions),
        provider=provider,
    )

    def refused(error: ProblemError) -> ActionRefusedError:
        return ActionRefusedError(str(error.extra.get("reason", "refused")), error.detail)

    async def write_draft(
        job_id: UUID, kind: str, contact: UUID | None, name: str | None, role: str | None
    ) -> UUID:
        body = DraftIn.model_validate(
            {
                "kind": kind,
                "recipient": RecipientIn(
                    contact_id=contact, name=None if contact else (name or HIRING_TEAM), role=role
                ),
                "recipient_kind": "hiring_manager" if contact is None and not name else None,
                "regenerate": True,
            }
        )
        try:
            started = await start_draft(drafts, job_id, body)
        except ProblemError as error:
            raise refused(error) from error
        return started.id

    async def tailor(job_id: UUID) -> UUID:
        try:
            await start_tailor(drafts, job_id, True)
        except ProblemError as error:
            raise refused(error) from error
        async with sessions() as session:
            row = await TailoredRepo(session).get_for_job(job_id)
        assert row is not None  # start_tailor just wrote it
        return row.id

    return ActionServices(
        queue=queue,
        job_cleanups=(clear_drafts_for_job,),
        start_draft=write_draft,
        start_tailor=tailor,
        start_search=start,
        start_mail_check=check_mail,
        careers=careers,
        rules_service=rules,
    )
