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
            )
        return Response(status_code=204)

    return router
