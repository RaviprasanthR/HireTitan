"""Connection endpoints (contracts/rest-api.md, Connection). Secrets never appear in a response."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from hiretitan.mail.application.connection import (
    ConnectionService,
    ConnectionView,
    NoCredentialsError,
)
from hiretitan.mail.application.ports import CredentialsFromEnvironmentError, SecretsFileError
from hiretitan.platform.web.problems import ProblemError

SETTINGS_PAGE = "/settings"


@dataclass(frozen=True)
class MailApiDeps:
    service: ConnectionService


class ConnectionModel(BaseModel):
    state: Literal["not_connected", "connected", "needs_reconnect"]
    address: str | None
    credentials_set: bool
    credentials_from_environment: bool
    redirect_uri: str
    last_check_started_at: datetime | None
    last_error: str | None
    window_hours: int

    @classmethod
    def of(cls, view: ConnectionView) -> ConnectionModel:
        return cls(
            state=view.state,
            address=view.address,
            credentials_set=view.credentials_set,
            credentials_from_environment=view.credentials_from_environment,
            redirect_uri=view.redirect_uri,
            last_check_started_at=view.last_check_started_at,
            last_error=view.last_error,
            window_hours=view.window_hours,
        )


class CredentialsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=10, max_length=300, pattern=r"^\S+$")
    client_secret: str = Field(min_length=10, max_length=300, pattern=r"^\S+$")


class AuthorizeModel(BaseModel):
    authorize_url: str


class DisconnectModel(BaseModel):
    revoked: bool  # False: Google was not reached; the person is told to remove it there


def _secrets_unreadable() -> ProblemError:
    return ProblemError(
        503,
        "The Google secrets file cannot be read. Disconnect to start again.",
        reason="secrets_unreadable",
    )


def create_connection_router(deps: MailApiDeps) -> APIRouter:
    router = APIRouter(prefix="/mail", tags=["mail"])
    service = deps.service

    @router.get("/connection")
    async def get_connection() -> ConnectionModel:
        return ConnectionModel.of(await service.view())

    @router.put("/credentials")
    async def put_credentials(body: CredentialsBody) -> ConnectionModel:
        try:
            await service.save_credentials(body.client_id, body.client_secret)
        except CredentialsFromEnvironmentError as error:
            raise ProblemError(
                409,
                "The Google client id and secret are set in the environment.",
                reason="credentials_from_environment",
            ) from error
        except SecretsFileError as error:
            raise _secrets_unreadable() from error
        return ConnectionModel.of(await service.view())

    @router.post("/connect")
    async def connect() -> AuthorizeModel:
        try:
            return AuthorizeModel(authorize_url=await service.start_consent())
        except NoCredentialsError as error:
            raise ProblemError(
                409, "Save your Google client id and secret first.", reason="no_credentials"
            ) from error
        except SecretsFileError as error:
            raise _secrets_unreadable() from error

    @router.get("/google/callback", include_in_schema=False)
    async def callback(
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
    ) -> RedirectResponse:
        outcome = await service.finish_callback(code=code, state=state, error=error)
        target = (
            f"{SETTINGS_PAGE}?gmail=connected"
            if outcome == "connected"
            else f"{SETTINGS_PAGE}?gmail=error&reason={outcome}"
        )
        return RedirectResponse(target, status_code=302, headers={"Cache-Control": "no-store"})

    @router.delete("/connection")
    async def disconnect() -> DisconnectModel:
        return DisconnectModel(revoked=await service.disconnect())

    return router
