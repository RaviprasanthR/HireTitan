"""Action definitions and the result shapes the model may see (002m research R3, R5).

An action's kind is part of its definition, never chosen by the model (FR-010):

* ``read``: changes nothing.
* ``small``: one item, applied at once, with a change record and an Undo; it must say how to
  undo and how to read the item's current fields (for the "changed since" check, EC-16).
* ``risky``: shown as a confirm card first; it must say which rows it touches, so the card can
  fingerprint them (R7).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.llm.port import ToolSpec

ActionKind = Literal["read", "small", "risky"]
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


class InvalidActionSpecError(ValueError):
    pass


class RunQueue(Protocol):
    async def enqueue(self, run_id: UUID, resume: Any = None) -> None: ...


@dataclass(frozen=True, slots=True)
class ActionServices:
    """What some actions need besides the database, built once by the wiring from the same
    objects the routes use: the job queue, a job's clean-ups, starting a search or a mail check."""

    queue: RunQueue | None = None
    job_cleanups: Sequence[Callable[[AsyncSession, UUID], Awaitable[None]]] = ()
    # (session, mode, now) -> the new search's id; raises the search use case's errors
    start_search: Callable[[AsyncSession, str, datetime], Awaitable[UUID]] | None = None
    # (now, read the last day again) -> the new check's search id; raises CheckNotReadyError
    start_mail_check: Callable[[datetime, bool], Awaitable[UUID]] | None = None
    # the careers-page reader the Companies page uses to confirm or reject a board
    careers: Any = None
    # session -> the RulesService the Search rules page uses (its synonyms and work areas)
    rules_service: Callable[[AsyncSession], Any] | None = None


@dataclass(frozen=True, slots=True)
class ActionContext:
    """What a handler gets besides its arguments: one session (one transaction), the time,
    and the services a few actions need."""

    session: AsyncSession
    now: datetime
    services: ActionServices = field(default_factory=ActionServices)


class ActionRefusedError(Exception):
    """Raised by targets when the change cannot even be proposed (a search already runs)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ReadResult:
    items: list[dict[str, Any]]
    total: int
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class PrivateItem:
    """A private item as the model sees it: a ref and a label built from non-private fields."""

    ref: str
    label: str


@dataclass(frozen=True, slots=True)
class PrivateResult:
    items: list[PrivateItem]
    total: int


@dataclass(frozen=True, slots=True)
class Applied:
    """What a small change did, for its change record and the person's notice (R6)."""

    target_kind: str
    target_id: UUID
    before: dict[str, Any]
    after: dict[str, Any]
    summary: str
    refs: list[str] = field(default_factory=list)
    created_rows: list[str] = field(default_factory=list)
    # work that must wait for the commit, like queuing a search on the worker (R7)
    after_commit: Callable[[], Awaitable[None]] | None = None


@dataclass(frozen=True, slots=True)
class ActionError:
    """A refusal the model and the person both see, e.g. ``not_found``, ``already_applied``."""

    reason: str
    message: str


@dataclass(frozen=True, slots=True)
class ChangeView:
    """The parts of a change record an undo handler needs."""

    target_kind: str
    target_id: UUID
    before: dict[str, Any]
    after: dict[str, Any]
    created_rows: list[str]


Handler = Callable[[ActionContext, Any], Awaitable[Any]]
UndoHandler = Callable[[ActionContext, ChangeView], Awaitable[None]]
CurrentFields = Callable[[ActionContext, UUID], Awaitable[Mapping[str, Any] | None]]
Targets = Callable[[ActionContext, Any], Awaitable[Mapping[str, Mapping[str, Any]]]]


@dataclass(frozen=True, slots=True)
class ActionSpec:
    name: str
    description: str
    args: type[BaseModel]
    kind: ActionKind
    handler: Handler
    private: bool = False
    undo: UndoHandler | None = None
    current: CurrentFields | None = None
    targets: Targets | None = None
    invalidate: tuple[str, ...] = ()  # front-end query keys to refresh after it ran
    # risky only: the card's first words ("Delete", "Start a search") and the arguments the
    # person may change on the card before confirming (never a ref: the targets stay fixed)
    card_title: str = ""
    editable: tuple[str, ...] = ()
    mirrors: tuple[
        str, ...
    ] = ()  # endpoints it does the same work as, e.g. "POST /jobs/{job_id}/applied"

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise InvalidActionSpecError(f"Bad action name {self.name!r}")
        if self.kind == "small" and (self.undo is None or self.current is None):
            raise InvalidActionSpecError(f"{self.name}: a small change needs undo and current")
        if self.kind == "risky" and self.targets is None:
            raise InvalidActionSpecError(f"{self.name}: a risky change needs targets")
        if self.kind == "read" and any((self.undo, self.current, self.targets)):
            raise InvalidActionSpecError(f"{self.name}: a read action changes nothing")


def to_tool_spec(spec: ActionSpec) -> ToolSpec:
    """What the model is told about an action: its name, purpose and arguments, nothing more."""
    return ToolSpec(
        name=spec.name, description=spec.description, parameters=spec.args.model_json_schema()
    )


def model_facing(result: ReadResult | PrivateResult) -> dict[str, Any]:
    """A result as it goes to the model. A private result is refs and labels, by construction."""
    if isinstance(result, PrivateResult):
        return {"items": [asdict(item) for item in result.items], "total": result.total}
    return {"items": result.items, "total": result.total, "truncated": result.truncated}
