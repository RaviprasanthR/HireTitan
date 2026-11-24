"""Start a mail check (contracts/rest-api.md, Checks). The check itself runs in the worker."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from hiretitan.mail.application.ports import CheckNotReadyError, CheckRuns
from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError

_ANSWERS = {
    "not_connected": "Connect Gmail first.",
    "needs_reconnect": "Gmail access has ended. Connect again first.",
    "search_running": "A search is already running.",
    "rules_not_approved": "Approve your search rules first.",
}


@dataclass(frozen=True)
class MailChecksApiDeps:
    runs: CheckRuns
    clock: ClockPort


class StartCheckBody(BaseModel):
    # FR-013e: forget which emails of the last 24 hours were read, so they are read again
    reread_last_day: bool = False


class StartedCheckOut(BaseModel):
    search_run_id: UUID


def create_checks_router(deps: MailChecksApiDeps) -> APIRouter:
    router = APIRouter(prefix="/mail", tags=["mail"])

    @router.post("/checks", status_code=202)
    async def start_check(body: StartCheckBody | None = None) -> StartedCheckOut:
        reread = body is not None and body.reread_last_day
        try:
            started = await deps.runs.start(trigger="button", now=deps.clock.now(), reread=reread)
        except CheckNotReadyError as error:
            reason = "rules_not_approved" if error.reason == "no_rules" else error.reason
            raise ProblemError(
                409, _ANSWERS.get(reason, "Cannot check now."), reason=reason
            ) from error
        return StartedCheckOut(search_run_id=started.search_run_id)

    return router
