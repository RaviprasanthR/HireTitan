"""Confirm or cancel a card, undo a change, and paste a job description from the composer
(002m contracts/rest-api.md; FR-010 to FR-014, FR-021)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.application.cards import (
    REFUSALS,
    CardFailedError,
    CardInvalidError,
    CardRefusedError,
    cancel_card,
    confirm_card,
)
from hiretitan.assistant.application.changes import (
    ChangeNotFoundError,
    UndoRefusedError,
    undo_change,
)
from hiretitan.platform.web.problems import ProblemError


class ItemEdit(BaseModel):
    index: int = Field(ge=0, le=24)
    args: dict[str, Any]


class ConfirmIn(BaseModel):
    items: list[ItemEdit] = []


class ConfirmOut(BaseModel):
    card_id: UUID
    state: str
    results: list[dict[str, Any]]


class UndoneOut(BaseModel):
    change_id: UUID
    undone: bool = True


class PasteIn(BaseModel):
    url: str = Field(max_length=2000)
    description: str = Field(max_length=40_000)
    title: str | None = Field(None, max_length=500)
    company: str | None = Field(None, max_length=500)
    location: str | None = Field(None, max_length=500)


def create_changes_router(deps: AssistantApiDeps) -> APIRouter:
    router = APIRouter(prefix="/assistant", tags=["assistant"])

    async def tell_tabs(keys: list[list[str]]) -> None:
        if deps.publish is not None and keys:
            await deps.publish(keys)

    @router.post("/cards/{card_id}/confirm", response_model=ConfirmOut)
    async def confirm(card_id: UUID, body: ConfirmIn | None = None) -> ConfirmOut:
        edits = {edit.index: edit.args for edit in (body.items if body else [])}
        try:
            outcome = await confirm_card(deps.cards, card_id, edits, deps.now())
        except CardRefusedError as error:
            status = REFUSALS[error.reason][0]
            raise ProblemError(status, str(error), reason=error.reason) from error
        except CardInvalidError as error:
            raise ProblemError(
                422,
                "Some values on the card are not valid.",
                reason="invalid",
                problems=error.problems,
            ) from error
        except CardFailedError as error:
            raise ProblemError(409, str(error), reason="failed") from error
        keys = [key for result in outcome.results for key in result.get("invalidate", [])]
        await tell_tabs(keys)
        return ConfirmOut(card_id=card_id, state="applied", results=outcome.results)

    @router.post("/cards/{card_id}/cancel", response_model=ConfirmOut)
    async def cancel(card_id: UUID) -> ConfirmOut:
        try:
            await cancel_card(deps.cards, card_id, deps.now())
        except CardRefusedError as error:
            status = REFUSALS[error.reason][0]
            raise ProblemError(status, str(error), reason=error.reason) from error
        return ConfirmOut(card_id=card_id, state="cancelled", results=[])

    @router.post("/changes/{change_id}/undo", response_model=UndoneOut)
    async def undo(change_id: UUID) -> UndoneOut:
        try:
            await undo_change(deps.undo, change_id, deps.now())
        except ChangeNotFoundError as error:
            raise ProblemError(404, "That change does not exist.", reason="not_found") from error
        except UndoRefusedError as error:
            raise ProblemError(409, str(error), reason=error.reason) from error
        await tell_tabs([["jobs"], ["companies"], ["pipeline"], ["interview"]])
        return UndoneOut(change_id=change_id)

    @router.post("/conversations/{conversation_id}/paste", status_code=201)
    async def paste(conversation_id: UUID, body: PasteIn) -> dict[str, Any]:
        """The composer's Paste a job description: the text goes to the paste use case and is
        never sent to the AI (FR-021). The job is added with an Undo, like a small change."""
        result = await deps.paste(conversation_id, body.model_dump())
        if "errors" in result:
            raise ProblemError(
                422, "The job could not be added.", reason="invalid", errors=result["errors"]
            )
        await tell_tabs([["jobs"]])
        return result

    return router
