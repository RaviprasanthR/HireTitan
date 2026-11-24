"""What Mikasa's application layer needs from the rest of the app (002m research R3, R9).

``assistant`` imports no feature module and not ``hiretitan.actions`` (import contract 9): the
catalogue, the stores and the profile-claim check reach it through these protocols, implemented
in ``assistant_wiring.py`` and ``assistant.infra``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from hiretitan.platform.llm.port import ToolSpec, Usage

ToolKind = Literal["read", "small", "risky", "unknown"]


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


@dataclass(frozen=True, slots=True)
class CallContext:
    conversation_id: UUID
    now: datetime


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

    async def record_round(self, rounds: LlmRound) -> None: ...


@dataclass(frozen=True, slots=True)
class AssistantStatus:
    """Whether Mikasa can be used now (FR-024); ``reason`` is ``key_missing``, ``key_rejected``,
    ``out_of_credit`` (with the provider's own message) or ``model_lacks_tools``."""

    available: bool
    reason: str | None = None
    provider_message: str | None = None
