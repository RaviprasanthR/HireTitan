"""Delete-all endpoint (contracts/rest-api.md, "Data")."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.storage.port import FileStoragePort
from hiretitan.setup.application.delete_all import DeleteAllStore, delete_all


@dataclass(frozen=True)
class DataApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    storage: FileStoragePort
    store: Callable[[AsyncSession], DeleteAllStore]
    enqueue_key_check: Callable[[], Awaitable[None]]
    # secrets kept in files, removed with everything else (the AI key saved in Settings, FR-033)
    forget_secrets: Callable[[], None] = lambda: None
    # Gmail handed back to Google before anything is removed (002c, FR-027)
    disconnect_mail: Callable[[], Awaitable[object]] | None = None


class DeleteAllIn(BaseModel):
    confirm: Literal["DELETE"]


def create_data_router(deps: DataApiDeps) -> APIRouter:
    router = APIRouter(prefix="/data", tags=["data"])

    @router.post("/delete-all", status_code=204)
    async def delete_everything(body: DeleteAllIn) -> Response:
        async with deps.sessions() as session:
            await delete_all(
                store=deps.store(session),
                storage=deps.storage,
                enqueue_key_check=deps.enqueue_key_check,
                forget_secrets=deps.forget_secrets,
                **({"disconnect_mail": deps.disconnect_mail} if deps.disconnect_mail else {}),
            )
        return Response(status_code=204)

    return router
