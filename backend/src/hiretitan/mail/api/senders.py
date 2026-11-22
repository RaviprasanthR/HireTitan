"""The sender list (contracts/rest-api.md, Senders): built-in senders can be switched off, the
person's own can be added and removed. Only these addresses are ever asked of Gmail (FR-009)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.domain.senders import SenderError
from hiretitan.mail.infra.models import MailSenderRow
from hiretitan.mail.infra.repos import BuiltInSenderError, SenderExistsError, SendersRepo
from hiretitan.platform.web.problems import ProblemError


@dataclass(frozen=True)
class MailSendersApiDeps:
    sessions: async_sessionmaker[AsyncSession]


class SenderOut(BaseModel):
    id: UUID
    address: str
    site: str
    built_in: bool
    enabled: bool

    @classmethod
    def of(cls, row: MailSenderRow) -> SenderOut:
        return cls(
            id=row.id,
            address=row.address,
            site=row.site,
            built_in=row.built_in,
            enabled=row.enabled,
        )


class SenderList(BaseModel):
    items: list[SenderOut]


class NewSender(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(max_length=1000)


class SenderSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


def _not_found() -> ProblemError:
    return ProblemError(404, "That sender is not on the list.", reason="not_found")


def create_senders_router(deps: MailSendersApiDeps) -> APIRouter:
    router = APIRouter(prefix="/mail/senders", tags=["mail"])

    @router.get("")
    async def list_senders() -> SenderList:
        async with deps.sessions() as session:
            return SenderList(
                items=[SenderOut.of(r) for r in await SendersRepo(session).list_all()]
            )

    @router.post("", status_code=201)
    async def add_sender(body: NewSender) -> SenderOut:
        async with deps.sessions() as session:
            try:
                row = await SendersRepo(session).add_custom(body.address)
            except SenderError as error:
                raise ProblemError(
                    422,
                    str(error),
                    reason="invalid_address",
                    errors=[{"field": "address", "message": str(error)}],
                ) from error
            except SenderExistsError as error:
                raise ProblemError(409, str(error), reason="sender_exists") from error
            await session.commit()
            return SenderOut.of(row)

    @router.patch("/{sender_id}")
    async def switch_sender(sender_id: UUID, body: SenderSwitch) -> SenderOut:
        async with deps.sessions() as session:
            repo = SendersRepo(session)
            if await repo.get(sender_id) is None:
                raise _not_found()
            await repo.set_enabled(sender_id, body.enabled)
            await session.commit()
            session.expire_all()
            row = await repo.get(sender_id)
            if row is None:  # removed between the two reads
                raise _not_found()
            return SenderOut.of(row)

    @router.delete("/{sender_id}", status_code=204)
    async def remove_sender(sender_id: UUID) -> Response:
        async with deps.sessions() as session:
            repo = SendersRepo(session)
            if await repo.get(sender_id) is None:
                raise _not_found()
            try:
                await repo.remove(sender_id)
            except BuiltInSenderError as error:
                raise ProblemError(409, str(error), reason="built_in") from error
            await session.commit()
        return Response(status_code=204)

    return router
