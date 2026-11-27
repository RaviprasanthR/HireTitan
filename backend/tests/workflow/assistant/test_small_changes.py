"""002m T020: small changes are applied at once with a change record, and Undo follows the rules
(FR-014, EC-03, EC-16, research R6).

A test-only small action (set a company's city) runs through the real catalogue adapter and the
real Undo unit on Postgres, so the rules are tested apart from any one feature's action.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.catalogue import Catalogue
from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, Applied, ChangeView
from hiretitan.assistant.application.changes import (
    ChangeNotFoundError,
    UndoRefusedError,
    undo_change,
)
from hiretitan.assistant.application.ports import CallContext
from hiretitan.assistant.infra.models import ChangeRow
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, undo_units
from hiretitan.search.infra.models import CompanyRow
from hiretitan.search.infra.repos import CompaniesRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)


class CityArgs(BaseModel):
    company: str
    city: str


async def _current(ctx: ActionContext, target_id: UUID) -> Mapping[str, Any] | None:
    row = await ctx.session.get(CompanyRow, target_id, populate_existing=True)
    return None if row is None else {"city": row.city}


async def _set_city(ctx: ActionContext, args: CityArgs) -> Applied | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    row = await ctx.session.get(CompanyRow, company_id)
    if row is None:
        return ActionError("not_found", "No such company.")
    before = {"city": row.city}
    row.city = args.city
    await ctx.session.flush()
    return Applied("company", company_id, before, {"city": args.city}, f"City set to {args.city}")


async def _undo(ctx: ActionContext, change: ChangeView) -> None:
    row = await ctx.session.get(CompanyRow, change.target_id)
    assert row is not None
    row.city = change.before["city"]
    await ctx.session.flush()


def catalogue() -> Catalogue:
    found = Catalogue()
    found.register(
        ActionSpec(
            name="set_company_city",
            description="Set a company's city",
            args=CityArgs,
            kind="small",
            handler=_set_city,
            undo=_undo,
            current=_current,
            invalidate=("companies",),
        )
    )
    return found


async def world(sessions: async_sessionmaker[AsyncSession]) -> tuple[UUID, UUID, UUID]:
    async with sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified", city="Pune"
        )
        conversation = await ConversationsRepo(session).create(now=NOW)
        message = await MessagesRepo(session).append(
            conversation.id, author="person", text="Acme is in Chennai", now=NOW
        )
        await session.commit()
        return company.id, conversation.id, message.id


async def city(sessions: async_sessionmaker[AsyncSession], company_id: UUID) -> str | None:
    async with sessions() as session:
        row = await session.get(CompanyRow, company_id)
        return row.city if row else None


async def apply(
    sessions: async_sessionmaker[AsyncSession],
    company_id: UUID,
    conversation: UUID,
    message: UUID,
    new_city: str,
) -> UUID:
    adapter = CatalogAdapter(catalogue(), sessions)
    outcome = await adapter.call(
        "set_company_city",
        json.dumps({"company": f"company:{company_id}", "city": new_city}),
        CallContext(conversation, NOW, message_id=message),
    )
    assert outcome.valid
    assert outcome.change is not None
    return outcome.change.change_id


async def test_FR014_small_change_applied_at_once_with_a_record(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    company_id, conversation, message = await world(sessions)
    adapter = CatalogAdapter(catalogue(), sessions)

    outcome = await adapter.call(
        "set_company_city",
        json.dumps({"company": f"company:{company_id}", "city": "Chennai"}),
        CallContext(conversation, NOW, message_id=message),
    )

    assert outcome.kind == "small"
    assert outcome.change is not None
    assert outcome.change.summary == "City set to Chennai"
    assert outcome.change.undo_until == NOW + timedelta(hours=24)
    assert outcome.change.invalidate == [["companies"]]
    assert outcome.payload["done"] == "City set to Chennai"
    assert await city(sessions, company_id) == "Chennai"
    async with sessions() as session:
        record = (await session.scalars(select(ChangeRow))).one()
    assert (record.message_id, record.before, record.after) == (
        message,
        {"city": "Pune"},
        {"city": "Chennai"},
    )


async def test_FR014_undo_restores(sessions: async_sessionmaker[AsyncSession]) -> None:
    company_id, conversation, message = await world(sessions)
    change_id = await apply(sessions, company_id, conversation, message, "Chennai")

    await undo_change(undo_units(catalogue(), sessions, lambda: NOW), change_id, NOW)

    assert await city(sessions, company_id) == "Pune"
    async with sessions() as session:
        record = await session.get(ChangeRow, change_id)
        assert record is not None
        assert record.undone_at == NOW


async def test_EC16_undo_refused_after_newer_change(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    company_id, conversation, message = await world(sessions)
    change_id = await apply(sessions, company_id, conversation, message, "Chennai")
    async with sessions() as session:  # the person edits the company on its page
        row = await session.get(CompanyRow, company_id)
        assert row is not None
        row.city = "Bengaluru"
        await session.commit()

    with pytest.raises(UndoRefusedError) as caught:
        await undo_change(undo_units(catalogue(), sessions, lambda: NOW), change_id, NOW)

    assert caught.value.reason == "changed_since"
    assert await city(sessions, company_id) == "Bengaluru"  # the newer change is kept


async def test_FR014_undo_refused_when_not_latest_or_too_late(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    company_id, conversation, message = await world(sessions)
    first = await apply(sessions, company_id, conversation, message, "Chennai")
    second = await apply(sessions, company_id, conversation, message, "Kochi")
    units = undo_units(catalogue(), sessions, lambda: NOW)

    with pytest.raises(UndoRefusedError) as older:
        await undo_change(units, first, NOW + timedelta(minutes=1))
    with pytest.raises(UndoRefusedError) as late:
        await undo_change(units, second, NOW + timedelta(hours=24))
    with pytest.raises(ChangeNotFoundError):
        await undo_change(units, UUID(int=1), NOW)

    assert (older.value.reason, late.value.reason) == ("not_latest", "too_late")
    assert await city(sessions, company_id) == "Kochi"


async def test_EC03_undo_twice_once(sessions: async_sessionmaker[AsyncSession]) -> None:
    company_id, conversation, message = await world(sessions)
    change_id = await apply(sessions, company_id, conversation, message, "Chennai")
    units = undo_units(catalogue(), sessions, lambda: NOW)

    results = await asyncio.gather(
        undo_change(units, change_id, NOW),
        undo_change(units, change_id, NOW),
        return_exceptions=True,
    )

    refused = [r for r in results if isinstance(r, UndoRefusedError)]
    assert len(refused) == 1
    assert refused[0].reason == "already_undone"
    assert await city(sessions, company_id) == "Pune"


async def test_FR014_action_refusal_records_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, conversation, message = await world(sessions)
    adapter = CatalogAdapter(catalogue(), sessions)

    outcome = await adapter.call(
        "set_company_city",
        json.dumps({"company": f"company:{UUID(int=5)}", "city": "Chennai"}),
        CallContext(conversation, NOW, message_id=message),
    )

    assert outcome.valid
    assert outcome.payload == {"error": "not_found", "message": "No such company."}
    assert outcome.change is None
    async with sessions() as session:
        assert (await session.scalars(select(ChangeRow))).all() == []
