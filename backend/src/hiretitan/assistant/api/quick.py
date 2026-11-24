"""Quick actions (002m FR-029, amended 2026-11-24): the list, a job's status, and a draft."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.application.quick import run_status
from hiretitan.assistant.application.turn import ConversationNotFoundError, TurnRunningError
from hiretitan.assistant.domain.quick import QUICK_ACTIONS, DraftKind, Form, Status
from hiretitan.platform.web.problems import ProblemError

RecipientKind = Literal["recruiter", "hiring_manager", "engineer", "other"]


def _job_ref(value: str) -> str:
    kind, _, rest = value.partition(":")
    if kind != "job":
        raise ValueError("Pick a job.")
    UUID(rest)  # raises ValueError
    return value


class QuickActionOut(BaseModel):
    key: str
    label: str
    form: Form
    draft_kind: DraftKind | None


class StatusIn(BaseModel):
    job: str = Field(max_length=60)
    status: Status

    _ref = field_validator("job")(_job_ref)


class QuickRunOut(BaseModel):
    message_id: UUID
    text: str
    refs: list[str]
    changes: list[dict[str, Any]]
    cards: list[dict[str, Any]]


def _refused(error: Exception) -> ProblemError:
    if isinstance(error, ConversationNotFoundError):
        return ProblemError(404, "That conversation does not exist.", reason="not_found")
    return ProblemError(409, "Mikasa is still answering your last message.", reason="turn_running")


def create_quick_router(deps: AssistantApiDeps) -> APIRouter:
    router = APIRouter(prefix="/assistant", tags=["assistant"])

    @router.get("/quick-actions", response_model=list[QuickActionOut])
    async def quick_actions() -> list[QuickActionOut]:
        return [
            QuickActionOut(key=a.key, label=a.label, form=a.form, draft_kind=a.draft_kind)
            for a in QUICK_ACTIONS
        ]

    @router.post("/conversations/{conversation_id}/quick/status", response_model=QuickRunOut)
    async def status(conversation_id: UUID, body: StatusIn) -> QuickRunOut:
        try:
            result = await run_status(deps.turn, conversation_id, body.job, body.status)
        except (ConversationNotFoundError, TurnRunningError) as error:
            raise _refused(error) from error
        return QuickRunOut(
            message_id=result.message_id,
            text=result.text,
            refs=result.refs,
            changes=[
                {
                    "change_id": str(c.change_id),
                    "action": c.action,
                    "summary": c.summary,
                    "undo_until": c.undo_until.isoformat() if c.undo_until else None,
                    "invalidate": c.invalidate,
                }
                for c in result.changes
            ],
            cards=[
                {
                    "card_id": str(c.card_id),
                    "summary": c.summary,
                    "items": c.items,
                    "expires_at": c.expires_at.isoformat(),
                }
                for c in result.cards
            ],
        )

    return router
