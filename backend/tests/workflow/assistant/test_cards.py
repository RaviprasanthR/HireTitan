"""002m T024: risky changes wait on a confirm card (FR-010 to FR-013, EC-02, EC-03, EC-05,
US2 scenario 4, US5 scenario 4; research R7).

Test-only risky actions (clear a company's city; clear several) run through the real catalogue
adapter and card unit on Postgres, so the card rules are tested apart from any one feature.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.catalogue import Catalogue
from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, Applied
from hiretitan.assistant.application.cards import (
    CardFailedError,
    CardInvalidError,
    CardRefusedError,
    cancel_card,
    confirm_card,
)
from hiretitan.assistant.application.ports import CallContext, ToolOutcome
from hiretitan.assistant.infra.models import CardRow, ChangeRow
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, card_units
from hiretitan.search.infra.models import CompanyRow
from hiretitan.search.infra.repos import CompaniesRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
queued: list[str] = []


class ClearArgs(BaseModel):
    company: str
    note: str = Field("", max_length=20)


class ClearManyArgs(BaseModel):
    companies: list[str] = Field(max_length=100)


async def _targets(ctx: ActionContext, args: ClearArgs) -> Mapping[str, Mapping[str, Any]]:
    company_id = Ref.parse(args.company, expect="company").id
    row = await ctx.session.get(CompanyRow, company_id, populate_existing=True)
    return {} if row is None else {f"company:{row.id}": {"label": row.name, "city": row.city}}


async def _clear(ctx: ActionContext, args: ClearArgs) -> Applied | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    row = await ctx.session.get(CompanyRow, company_id)
    if row is None:
        return ActionError("not_found", "No such company.")
    if args.note == "fail":
        return ActionError("refused", "This one cannot be cleared.")
    before = {"city": row.city}
    row.city = None
    await ctx.session.flush()

    async def queue() -> None:
        queued.append(args.company)

    return Applied(
        "company", row.id, before, {"city": None}, f"Cleared {row.name}", after_commit=queue
    )


async def _many_targets(ctx: ActionContext, args: ClearManyArgs) -> Mapping[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    for ref in args.companies:
        found.update(await _targets(ctx, ClearArgs(company=ref)))
    return found


async def _clear_many(ctx: ActionContext, args: ClearManyArgs) -> Applied | ActionError:
    last: Applied | ActionError = ActionError("not_found", "Nothing to clear.")
    for ref in args.companies:
        last = await _clear(ctx, ClearArgs(company=ref))
        if isinstance(last, ActionError):
            return last
    return last


def catalogue() -> Catalogue:
    found = Catalogue()
    found.register(
        ActionSpec(
            name="clear_city",
            description="Clear a company's city",
            args=ClearArgs,
            kind="risky",
            handler=_clear,
            targets=_targets,
            card_title="Clear the city of",
            editable=("note",),
            invalidate=("companies",),
        )
    )
    found.register(
        ActionSpec(
            name="clear_cities",
            description="Clear several companies' cities",
            args=ClearManyArgs,
            kind="risky",
            handler=_clear_many,
            targets=_many_targets,
            card_title="Clear the city of",
        )
    )
    return found


class World:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions
        self.adapter = CatalogAdapter(catalogue(), sessions)
        self.units = card_units(catalogue(), sessions, lambda: NOW)

    async def setup(self) -> None:
        queued.clear()
        async with self.sessions() as session:
            self.conversation = (await ConversationsRepo(session).create(now=NOW)).id
            self.message = (
                await MessagesRepo(session).append(
                    self.conversation, author="person", text="clear it", now=NOW
                )
            ).id
            await session.commit()

    async def company(self, name: str = "Acme", city: str = "Pune") -> UUID:
        async with self.sessions() as session:
            row = await CompaniesRepo(session).add(
                name=name, origin="user", resolution="verified", city=city
            )
            await session.commit()
            return row.id

    async def city(self, company_id: UUID) -> str | None:
        async with self.sessions() as session:
            row = await session.get(CompanyRow, company_id)
            return row.city if row else None

    async def propose(self, action: str = "clear_city", **args: Any) -> ToolOutcome:
        return await self.adapter.call(
            action,
            json.dumps(args),
            CallContext(self.conversation, NOW, message_id=self.message),
        )


@pytest.fixture
async def world(sessions: async_sessionmaker[AsyncSession]) -> World:
    found = World(sessions)
    await found.setup()
    return found


async def test_US2_AS4_risky_needs_confirm(world: World) -> None:
    acme = await world.company()

    outcome = await world.propose(company=f"company:{acme}")

    assert outcome.card is not None
    assert outcome.card.summary == "Clear the city of: Acme"  # written by HireTitan, not the AI
    assert outcome.payload["note"].startswith("Nothing has changed yet")
    assert await world.city(acme) == "Pune"  # nothing changed

    applied = await confirm_card(world.units, outcome.card.card_id, {}, NOW)

    assert await world.city(acme) is None
    assert applied.results[0]["summary"] == "Cleared Acme"
    assert queued == [f"company:{acme}"]  # queued only after the commit
    async with world.sessions() as session:
        card = await session.get(CardRow, outcome.card.card_id)
        assert card is not None
        assert card.state == "applied"
        change = (await session.scalars(select(ChangeRow))).one()
        assert (change.card_id, change.message_id) == (outcome.card.card_id, None)


async def test_US2_AS4_cancel_changes_nothing(world: World) -> None:
    acme = await world.company()
    outcome = await world.propose(company=f"company:{acme}")
    assert outcome.card is not None

    await cancel_card(world.units, outcome.card.card_id, NOW)

    assert await world.city(acme) == "Pune"
    with pytest.raises(CardRefusedError) as caught:
        await confirm_card(world.units, outcome.card.card_id, {}, NOW)
    assert caught.value.reason == "not_proposed"


async def test_FR011_edited_values_used(world: World) -> None:
    acme = await world.company()
    outcome = await world.propose(company=f"company:{acme}")
    assert outcome.card is not None

    with pytest.raises(CardInvalidError):
        await confirm_card(world.units, outcome.card.card_id, {0: {"note": "x" * 21}}, NOW)
    with pytest.raises(CardFailedError):  # an edit that makes the action refuse
        await confirm_card(world.units, outcome.card.card_id, {0: {"note": "fail"}}, NOW)

    assert await world.city(acme) == "Pune"


async def test_FR011_only_editable_fields_change(world: World) -> None:
    acme = await world.company()
    other = await world.company("Globex", "Delhi")
    outcome = await world.propose(company=f"company:{acme}")
    assert outcome.card is not None

    await confirm_card(world.units, outcome.card.card_id, {0: {"company": f"company:{other}"}}, NOW)

    assert (await world.city(acme), await world.city(other)) == (None, "Delhi")


async def test_FR012_all_or_nothing(world: World) -> None:
    acme = await world.company()
    globex = await world.company("Globex", "Delhi")
    outcome = await world.propose(
        "clear_cities", companies=[f"company:{acme}", f"company:{UUID(int=9)}", f"company:{globex}"]
    )
    assert outcome.card is not None
    # the middle ref has no target, so only two are fingerprinted; it fails on apply

    with pytest.raises(CardFailedError):
        await confirm_card(world.units, outcome.card.card_id, {}, NOW)

    assert (await world.city(acme), await world.city(globex)) == ("Pune", "Delhi")
    async with world.sessions() as session:
        card = await session.get(CardRow, outcome.card.card_id)
        assert card is not None
        assert card.state == "failed"


async def test_EC02_stale_card_refused(world: World) -> None:
    acme = await world.company()
    outcome = await world.propose(company=f"company:{acme}")
    assert outcome.card is not None
    async with world.sessions() as session:  # changed on the Companies page meanwhile
        row = await session.get(CompanyRow, acme)
        assert row is not None
        row.city = "Mumbai"
        await session.commit()

    with pytest.raises(CardRefusedError) as caught:
        await confirm_card(world.units, outcome.card.card_id, {}, NOW)

    assert caught.value.reason == "stale"
    assert await world.city(acme) == "Mumbai"


async def test_EC03_double_confirm_applies_once(world: World) -> None:
    acme = await world.company()
    outcome = await world.propose(company=f"company:{acme}")
    assert outcome.card is not None

    results = await asyncio.gather(
        confirm_card(world.units, outcome.card.card_id, {}, NOW),
        confirm_card(world.units, outcome.card.card_id, {}, NOW),
        return_exceptions=True,
    )

    assert sum(isinstance(r, CardRefusedError) for r in results) == 1
    async with world.sessions() as session:
        assert len((await session.scalars(select(ChangeRow))).all()) == 1
    assert queued == [f"company:{acme}"]


async def test_EC05_bulk_limit(world: World) -> None:
    refs = [f"company:{await world.company(f'Co {n}')}" for n in range(26)]

    outcome = await world.propose("clear_cities", companies=refs)

    assert outcome.card is None
    assert outcome.payload["error"] == "bulk_limit"
    many = await world.propose("clear_cities", companies=refs[:7])
    assert many.card is not None
    assert many.card.summary.endswith("and 2 more")


async def test_US5_AS4_old_card_expired(world: World) -> None:
    acme = await world.company()
    outcome = await world.propose(company=f"company:{acme}")
    assert outcome.card is not None

    with pytest.raises(CardRefusedError) as caught:
        await confirm_card(world.units, outcome.card.card_id, {}, NOW + timedelta(minutes=30))

    assert caught.value.reason == "expired"
    assert await world.city(acme) == "Pune"
    async with world.sessions() as session:
        card = await session.get(CardRow, outcome.card.card_id)
        assert card is not None
        assert card.state == "expired"
