"""What Mikasa's application layer needs from the rest of the app (002m research R3, R9).

``assistant`` imports no feature module and not ``hiretitan.actions`` (import contract 9): the
catalogue, the stores and the profile-claim check reach it through these protocols, implemented
in ``assistant_wiring.py`` and ``assistant.infra``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from hiretitan.platform.llm.port import ToolSpec, Usage

ToolKind = Literal["read", "small", "risky", "unknown"]


@dataclass(frozen=True, slots=True)
class CardNotice:
    """A risky change waiting for the person's confirmation (R7)."""

    card_id: UUID
    summary: str
    items: list[dict[str, Any]]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """What one tool call did, as the turn loop sees it.

    ``valid`` is False when the call itself was wrong (an unknown tool, arguments that fail the
    action's model): ``problem`` then says why, for the one repair (R9). Otherwise ``payload``
    is the model-facing result (already refs and labels for private actions) and ``refs`` the
    items it named.
    """

    kind: ToolKind
    valid: bool
    payload: dict[str, Any] = field(default_factory=dict)
    refs: list[str] = field(default_factory=list)
    problem: str | None = None
    change: ChangeNotice | None = None  # set when a small change was applied
    card: CardNotice | None = None  # set when a risky change waits for the person


@dataclass(frozen=True, slots=True)
class CallContext:
    conversation_id: UUID
    now: datetime
    message_id: UUID | None = None  # the person's message the call answers; a change hangs on it


@dataclass(frozen=True, slots=True)
class ChangeNotice:
    """A small change that was applied at once (R6): what the person sees, and its Undo."""

    change_id: UUID
    action: str
    summary: str
    undo_until: datetime | None
    invalidate: list[list[str]] = field(default_factory=list)


class ActionCatalog(Protocol):
    def tool_specs(self) -> list[ToolSpec]: ...

    async def call(self, name: str, arguments_json: str, ctx: CallContext) -> ToolOutcome: ...


class ProfileClaimsChecker(Protocol):
    """Constitution II for replies (FR-018a): the numbers, skills, employers, titles and dates
    in ``text`` that the confirmed profile does not back. Empty when the reply is fine.

    ``context`` is what the turn's other actions returned (job titles, company names, dates):
    a reply may name those, but never claim them as the person's own experience."""

    async def unbacked(self, text: str, context: str) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class StoredMessage:
    id: UUID
    author: str
    text: str
    refs: list[str]


@dataclass(frozen=True, slots=True)
class LlmRound:
    """One model round inside a turn, for the call log (constitution IV, FR-023)."""

    prompt_name: str
    prompt_version: str
    provider: str
    model: str
    usage: Usage
    outcome: str


class TurnStore(Protocol):
    async def conversation_exists(self, conversation_id: UUID) -> bool: ...

    async def claim_turn(self, conversation_id: UUID, now: datetime) -> bool: ...

    async def release_turn(self, conversation_id: UUID) -> None: ...

    async def add_person_message(
        self, conversation_id: UUID, text: str, signals: Sequence[dict[str, Any]], now: datetime
    ) -> UUID: ...

    async def add_mikasa_message(
        self,
        conversation_id: UUID,
        *,
        text: str,
        status: str,
        refs: Sequence[str],
        tool_trace: Sequence[dict[str, Any]],
        error: dict[str, Any] | None,
        now: datetime,
    ) -> UUID: ...

    async def recent(self, conversation_id: UUID, count: int) -> list[StoredMessage]: ...

    async def known_refs(self, conversation_id: UUID) -> set[str]: ...

    async def last_person_text(self, conversation_id: UUID) -> str | None: ...

    async def record_round(self, rounds: LlmRound) -> None: ...


@dataclass(frozen=True, slots=True)
class AssistantStatus:
    """Whether Mikasa can be used now (FR-024); ``reason`` is ``key_missing``, ``key_rejected``,
    ``out_of_credit`` (with the provider's own message) or ``model_lacks_tools``."""

    available: bool
    reason: str | None = None
    provider_message: str | None = None


@dataclass(frozen=True, slots=True)
class ChangeRecord:
    id: UUID
    action: str
    target_kind: str
    target_id: UUID
    before: dict[str, Any]
    after: dict[str, Any]
    created_rows: list[str]
    undoable_until: datetime | None
    undone_at: datetime | None


class UndoUnit(Protocol):
    """One transaction for one Undo (R6): the change row is locked when read, so two Undo
    presses at once apply once (EC-03)."""

    async def change(self, change_id: UUID) -> ChangeRecord | None: ...

    async def is_latest(self, change: ChangeRecord) -> bool: ...

    async def current(self, change: ChangeRecord) -> Mapping[str, Any] | None: ...

    async def run_undo(self, change: ChangeRecord) -> None: ...

    async def mark_undone(self, change_id: UUID, now: datetime) -> None: ...

    async def commit(self) -> None: ...


UndoUnitFactory = Callable[[], AbstractAsyncContextManager[UndoUnit]]


@dataclass(frozen=True, slots=True)
class CardRecord:
    id: UUID
    conversation_id: UUID
    state: str
    items: list[dict[str, Any]]
    fingerprints: dict[str, str]
    expires_at: datetime


@dataclass
class ApplyOutcome:
    """What applying a card's items did, inside its one transaction."""

    ok: bool
    error: str | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    after_commit: list[Callable[[], Awaitable[None]]] = field(default_factory=list)


class CardUnit(Protocol):
    """One transaction for one confirm (R7). ``claim`` moves ``proposed`` to ``applying`` in one
    statement, so a second confirm finds nothing (EC-03)."""

    async def card(self, card_id: UUID) -> CardRecord | None: ...

    async def problems(self, items: list[dict[str, Any]]) -> list[str]: ...

    async def fingerprints(self, items: list[dict[str, Any]]) -> dict[str, str]: ...

    async def claim(self, card_id: UUID, now: datetime) -> bool: ...

    async def apply(
        self, card: CardRecord, items: list[dict[str, Any]], now: datetime
    ) -> ApplyOutcome: ...

    async def set_state(
        self, card_id: UUID, state: str, now: datetime, result: list[Any] | None = None
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


CardUnitFactory = Callable[[], AbstractAsyncContextManager[CardUnit]]


@dataclass(frozen=True, slots=True)
class StartedDraft:
    """A draft the drafts workflow is now writing, and the job it is for, in words."""

    draft_id: UUID
    job_label: str


class DraftRefusedError(Exception):
    """The draft cannot be started (no profile, no AI key, one is still being written...)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DraftStarter(Protocol):
    """Starts a draft through the drafts use case (002m quick actions). A missing name means the
    hiring team. Raises ``DraftRefusedError``."""

    async def __call__(
        self, job_id: UUID, kind: str, name: str | None, recipient_kind: str | None
    ) -> StartedDraft: ...


StagedStep = Literal["need_post", "need_details", "need_kind", "drafting", "ask_save", "done"]


@dataclass(frozen=True, slots=True)
class StagedView:
    """Where the chat's post-to-draft flow stands (002m quick flow)."""

    step: StagedStep
    kind: str | None = None
    label: str | None = None  # "Backend Engineer at Acme", once a post is held
    job_ref: str | None = None
    draft_ref: str | None = None
    already_saved: bool = False  # the post was a job the person already had


class StagedRefusedError(Exception):
    """The step cannot be done now; ``message`` says why in words."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class StagedFlow(Protocol):
    """The post-to-draft flow of a conversation: choose a draft, paste a post, get the draft,
    then say yes or no to saving the job. Nothing is saved before the yes."""

    async def view(self, conversation_id: UUID) -> StagedView | None: ...

    async def begin(self, conversation_id: UUID, kind: str) -> StagedView: ...

    async def hold_post(self, conversation_id: UUID, text: str) -> StagedView: ...

    async def details(self, conversation_id: UUID, title: str, company: str) -> StagedView: ...

    async def choose(self, conversation_id: UUID, kind: str) -> StagedView: ...

    async def save(self, conversation_id: UUID) -> str: ...

    async def discard(self, conversation_id: UUID) -> None: ...
