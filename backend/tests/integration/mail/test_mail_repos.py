"""Mail repositories (T007): FR-004, FR-010, FR-011, US3 AS6. Real PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.mail_env import make_run

from hiretitan.mail.domain.senders import SeedSender
from hiretitan.mail.infra.repos import (
    BuiltInSenderError,
    ConnectionRepo,
    MailChecksRepo,
    ReadMessagesRepo,
    SenderExistsError,
    SendersRepo,
)
from hiretitan.mail_wiring import seed_mail_senders

NOW = datetime(2026, 11, 18, 9, tzinfo=UTC)
SEED = (
    SeedSender("linkedin", "jobs@linkedin.example.invalid"),
    SeedSender("naukri", "alerts@naukri.example.invalid"),
)


async def test_FR004_connection_is_saved_updated_and_deleted(db_session: AsyncSession) -> None:
    repo = ConnectionRepo(db_session)
    assert await repo.get() is None

    await repo.connect("person@example.invalid", NOW)
    await repo.connect("person@example.invalid", NOW + timedelta(days=1))  # a reconnect updates it
    row = await repo.get()
    assert row is not None
    assert (row.address, row.state, row.connected_at) == (
        "person@example.invalid",
        "connected",
        NOW + timedelta(days=1),
    )

    await repo.set_state("needs_reconnect", "Gmail access has ended.")
    row = await repo.get()
    assert row is not None
    assert (row.state, row.last_error) == ("needs_reconnect", "Gmail access has ended.")

    await repo.connect("person@example.invalid", NOW)  # reconnecting clears the error
    row = await repo.get()
    assert row is not None
    assert (row.state, row.last_error) == ("connected", None)

    await repo.mark_check_started(NOW)
    row = await repo.get()
    assert row is not None
    assert row.last_check_started_at == NOW

    await repo.remove()
    assert await repo.get() is None


async def test_FR010_seed_merge_keeps_switches(db_session: AsyncSession) -> None:
    repo = SendersRepo(db_session)
    assert await repo.merge_seed(SEED) == 2
    first = (await repo.list_all())[0]
    await repo.set_enabled(first.id, False)

    assert await repo.merge_seed((*SEED, SeedSender("indeed", "alert@indeed.example.invalid"))) == 1

    by_address = {s.address: s for s in await repo.list_all()}
    assert by_address[first.address].enabled is False  # the person's switch survives a new release
    assert by_address["alert@indeed.example.invalid"].enabled is True
    assert all(s.built_in for s in by_address.values())


async def test_FR009_only_enabled_senders_are_asked_for(db_session: AsyncSession) -> None:
    repo = SendersRepo(db_session)
    await repo.merge_seed(SEED)
    senders = {s.address: s for s in await repo.list_all()}
    await repo.set_enabled(senders["jobs@linkedin.example.invalid"].id, False)
    await repo.add_custom("digest@board.example.invalid")

    assert await repo.enabled_addresses() == [
        "alerts@naukri.example.invalid",
        "digest@board.example.invalid",
    ]


async def test_FR010_a_sender_the_person_added_can_be_removed_a_built_in_cannot(
    db_session: AsyncSession,
) -> None:
    repo = SendersRepo(db_session)
    await repo.merge_seed(SEED)
    custom = await repo.add_custom("Digest@Board.Example.Invalid")
    assert (custom.address, custom.site, custom.built_in) == (
        "digest@board.example.invalid",
        "other",
        False,
    )
    with pytest.raises(SenderExistsError):
        await repo.add_custom("digest@board.example.invalid")
    with pytest.raises(SenderExistsError):
        await repo.add_custom("jobs@linkedin.example.invalid")  # already built in

    builtin = (await repo.list_all())[0]
    with pytest.raises(BuiltInSenderError):
        await repo.remove(builtin.id)
    await repo.remove(custom.id)

    assert custom.address not in [s.address for s in await repo.list_all()]


async def test_FR011_read_once(db_session: AsyncSession) -> None:
    repo = ReadMessagesRepo(db_session)
    await repo.record("m1", "a@x.example.invalid", NOW, "read", "naukri", 4, [], None, NOW)
    await repo.record("m2", "a@x.example.invalid", NOW, "no_jobs", "naukri", 0, [], None, NOW)

    assert await repo.already_read(["m1", "m2", "m3"]) == {"m1", "m2"}
    assert await repo.already_read([]) == set()


async def test_US3_AS6_needs_ai_is_read_again(db_session: AsyncSession) -> None:
    repo = ReadMessagesRepo(db_session)
    await repo.record("m1", "a@x.example.invalid", NOW, "needs_ai", None, 0, [], None, NOW)

    assert await repo.already_read(["m1"]) == set()  # waiting for the AI: read again next time

    await repo.record(
        "m1", "a@x.example.invalid", NOW, "read", "ai", 2, [{"rule_id": "x"}], None, NOW
    )
    assert await repo.already_read(["m1"]) == {"m1"}
    assert await repo.count() == 1  # the same record was updated, not a second one added


async def test_FR011_a_late_needs_ai_cannot_undo_a_final_read(db_session: AsyncSession) -> None:
    repo = ReadMessagesRepo(db_session)
    await repo.record("m1", "a@x.example.invalid", NOW, "read", "ai", 2, [], None, NOW)

    # a second, slower check records the same message as waiting for the AI
    await repo.record("m1", "a@x.example.invalid", NOW, "needs_ai", None, 0, [], None, NOW)

    assert await repo.already_read(["m1"]) == {"m1"}


async def test_FR010_two_adds_of_one_sender_do_not_crash(db_session: AsyncSession) -> None:
    repo = SendersRepo(db_session)
    first = await repo.add_custom("digest@board.example.invalid")
    with pytest.raises(SenderExistsError):
        await repo.add_custom("digest@board.example.invalid")
    # the session is still usable after the refused add (no half-done transaction)
    assert [s.id for s in await repo.list_all()] == [first.id]


async def test_FR010_merge_seed_twice_in_one_session_adds_once(db_session: AsyncSession) -> None:
    repo = SendersRepo(db_session)
    assert await repo.merge_seed(SEED) == 2
    assert await repo.merge_seed(SEED) == 0


async def test_FR004_connect_twice_keeps_one_row(db_session: AsyncSession) -> None:
    repo = ConnectionRepo(db_session)
    await repo.connect("a@example.invalid", NOW)
    await repo.connect("b@example.invalid", NOW)

    row = await repo.get()
    assert row is not None
    assert row.address == "b@example.invalid"


async def test_FR004_disconnect_removes_read_email_and_check_records(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session)
    checks = MailChecksRepo(db_session)
    check = await checks.create(run_id, "button", NOW)
    await ReadMessagesRepo(db_session).record(
        "m1", "a@x.example.invalid", NOW, "read", "naukri", 1, [], check.id, NOW
    )

    await ReadMessagesRepo(db_session).clear()
    await checks.clear()

    assert await ReadMessagesRepo(db_session).count() == 0
    assert await checks.get_for_run(run_id) is None


async def test_FR026_a_check_is_finished_with_its_counts(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    checks = MailChecksRepo(db_session)
    check = await checks.create(run_id, "daily", NOW)

    await checks.finish(
        check.id, listed=5, skipped=1, read=3, unreadable=1, more_remaining=False, ended="finished"
    )

    row = await checks.get_for_run(run_id)
    assert row is not None
    assert (row.emails_listed, row.emails_read, row.ended) == (5, 3, "finished")


async def test_FR010_seed_loaded_at_api_start(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    seed = tmp_path / "mail_senders.yaml"
    seed.write_text(
        "senders:\n  linkedin:\n    - jobs@linkedin.example.invalid\n  naukri:\n"
        "    - alerts@naukri.example.invalid\n",
        encoding="utf-8",
    )

    assert await seed_mail_senders(sessions, seed) == 2
    assert await seed_mail_senders(sessions, seed) == 0  # a second start adds nothing

    async with sessions() as session:
        assert len(await SendersRepo(session).list_all()) == 2
    assert await seed_mail_senders(sessions, tmp_path / "missing.yaml") == 0  # no file, no seed


async def test_FR010_delete_all_my_data_reseeds_the_alert_senders(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    from hiretitan.setup_wiring import SqlDeleteAllStore

    seed = tmp_path / "mail_senders.yaml"
    seed.write_text("senders:\n  naukri:\n    - alerts@naukri.example.invalid\n", encoding="utf-8")
    senders = SendersRepo(db_session)
    await senders.add_custom("digest@board.example.invalid")
    await db_session.commit()

    await SqlDeleteAllStore(db_session, mail_seed=seed).wipe_and_reseed()

    # the person's own sender is gone, the shipped one is back, as on a fresh install
    assert [s.address for s in await senders.list_all()] == ["alerts@naukri.example.invalid"]
