"""Importing a company sheet: matching, contacts, notes, preview and idempotence (T011).

Real PostgreSQL, the 002 test seed (Example Alpha, Beta, Gamma) and the synthetic sample sheet.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.application.seed import load_seed
from hiretitan.search.application.sheet_import import SheetOutcome, apply_sheet, preview_sheet
from hiretitan.search.domain.contacts import ContactFields, name_key
from hiretitan.search.domain.sheet import read
from hiretitan.search.infra.models import ContactRow
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo

FIXTURES = Path(__file__).parents[2] / "fixtures"
SEED_V1 = FIXTURES / "companies" / "seed_v1.yaml"
SAMPLE = FIXTURES / "sheets" / "product_companies_sample.csv"
EXPECTED_CONTACTS = 30  # fixtures/sheets/README.md (SC-001)


def sheet(*rows: list[str]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Company", "City", "Website", "Careers page", "Contacts", "Notes"])
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


async def seeded(session: AsyncSession) -> CompaniesRepo:
    repo = CompaniesRepo(session)
    await load_seed(repo, SEED_V1)
    return repo


async def run_apply(session: AsyncSession, source: str) -> SheetOutcome:
    layout, rows = read(source)
    return await apply_sheet(
        CompaniesRepo(session), ContactsRepo(session), NotesRepo(session), layout, rows
    )


async def run_preview(session: AsyncSession, source: str) -> SheetOutcome:
    layout, rows = read(source)
    return await preview_sheet(
        CompaniesRepo(session), ContactsRepo(session), NotesRepo(session), layout, rows
    )


async def count(session: AsyncSession, table: str) -> int:
    return int((await session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar_one())


async def contacts_of(session: AsyncSession, name: str) -> list[ContactRow]:
    companies = await CompaniesRepo(session).list_filtered("all")
    company = next(c for c in companies if c.name == name)
    return list(await ContactsRepo(session).list_for_company(company.id))


async def test_US1_AS1_contacts_attach_and_shipped_facts_unchanged(
    db_session: AsyncSession,
) -> None:
    repo = await seeded(db_session)
    before = {c.name: (c.city, c.website, c.careers_url, c.board_id) for c in await repo.list_all()}

    await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    after = {c.name: (c.city, c.website, c.careers_url, c.board_id) for c in await repo.list_all()}
    for name in ("Example Alpha", "Example Beta", "Example Gamma"):
        assert after[name] == before[name]  # FR-004: a built-in company's facts never change
    assert len(await contacts_of(db_session, "Example Alpha")) == 3


async def test_US1_AS2_unknown_company_added_as_own(db_session: AsyncSession) -> None:
    repo = await seeded(db_session)

    await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    delta = next(c for c in await repo.list_all() if c.name == "Sample Delta Pvt Ltd")
    assert delta.origin == "user"
    assert delta.resolution == "unresolved"  # still to be discovered and confirmed
    assert delta.careers_url == "https://delta.example.test/careers"
    assert delta.city == "Mumbai"


async def test_US1_AS2_row_without_careers_link_is_added_unresolved(
    db_session: AsyncSession,
) -> None:
    repo = await seeded(db_session)

    await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    zeta = next(c for c in await repo.list_all() if c.name == "Sample Zeta")
    assert zeta.careers_url is None
    assert zeta.resolution == "unresolved"


async def test_SC001_every_named_contact_in_the_sample_is_attached(
    db_session: AsyncSession,
) -> None:
    await seeded(db_session)

    outcome = await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    assert await count(db_session, "company_contacts") == EXPECTED_CONTACTS
    assert outcome.contacts_added == EXPECTED_CONTACTS
    assert (outcome.matched, outcome.companies_added, len(outcome.skipped)) == (3, 8, 2)


async def test_edge_same_name_at_two_companies_stays_two_contacts(
    db_session: AsyncSession,
) -> None:
    await seeded(db_session)

    await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    theta = await contacts_of(db_session, "Sample Theta")
    iota = await contacts_of(db_session, "Sample Iota")
    assert [c.name for c in theta] == ["Sam Sample"]
    assert [c.name for c in iota] == ["Sam Sample"]
    assert theta[0].id != iota[0].id


async def test_US1_AS3_contacts_created_with_four_facts(db_session: AsyncSession) -> None:
    await seeded(db_session)

    await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    jane = next(
        c for c in await contacts_of(db_session, "Example Alpha") if c.name == "Jane Example"
    )
    assert jane.role == "Recruiter"
    assert jane.confidence == "high"
    assert jane.linkedin_url == "https://www.linkedin.com/in/jane-example"
    assert jane.source == "import"
    assert jane.link_key == "linkedin.com/in/jane-example"


async def test_US1_AS4_skipped_rows_save_nothing(db_session: AsyncSession) -> None:
    repo = await seeded(db_session)

    outcome = await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    reasons = {s.line: s.reason for s in outcome.skipped}
    assert len(reasons) == 2
    assert any("no company name" in r.lower() for r in reasons.values())
    ambiguous = next(r for r in reasons.values() if "two companies" in r.lower())
    assert "Example Alpha" in ambiguous
    assert "Example Beta" in ambiguous
    names = {c.name for c in await repo.list_all()}
    assert "noname" not in " ".join(names).lower()
    rows = await db_session.execute(text("SELECT name FROM app.company_contacts"))
    assert "Skipped Person" not in {r[0] for r in rows}
    assert await count(db_session, "companies") == 3 + 8


async def test_US1_AS5_second_import_changes_nothing(db_session: AsyncSession) -> None:
    await seeded(db_session)
    source = SAMPLE.read_text(encoding="utf-8")
    await run_apply(db_session, source)
    snapshot = (await count(db_session, "companies"), await count(db_session, "company_contacts"))
    notes_before = await count(db_session, "company_notes")

    preview = await run_preview(db_session, source)
    again = await run_apply(db_session, source)

    for outcome in (preview, again):
        assert outcome.companies_added == 0
        assert outcome.contacts_added == 0
        assert outcome.contacts_updated == 0
        assert (outcome.notes_set, outcome.notes_changed) == (0, 0)
    assert again.matched == 11
    assert snapshot == (
        await count(db_session, "companies"),
        await count(db_session, "company_contacts"),
    )
    assert notes_before == await count(db_session, "company_notes")


async def test_US1_AS5_changed_role_or_link_updates_not_duplicates(
    db_session: AsyncSession,
) -> None:
    await seeded(db_session)
    first = sheet(
        ["Example Alpha", "", "", "", "Jane Example - Recruiter\nhttps://linkedin.com/in/jane", ""]
    )
    await run_apply(db_session, first)

    role_changed = sheet(
        [
            "Example Alpha",
            "",
            "",
            "",
            "Jane Example - Talent Lead\nhttps://linkedin.com/in/jane",
            "",
        ]
    )
    outcome = await run_apply(db_session, role_changed)
    assert (outcome.contacts_added, outcome.contacts_updated) == (0, 1)
    (jane,) = await contacts_of(db_session, "Example Alpha")
    assert jane.role == "Talent Lead"

    link_changed = sheet(
        [
            "Example Alpha",
            "",
            "",
            "",
            "Jane Example - Talent Lead\nhttps://linkedin.com/in/jane-new",
            "",
        ]
    )
    outcome = await run_apply(db_session, link_changed)
    assert (outcome.contacts_added, outcome.contacts_updated) == (0, 1)
    (jane,) = await contacts_of(db_session, "Example Alpha")
    assert jane.link_key == "linkedin.com/in/jane-new"

    renamed = sheet(
        [
            "Example Alpha",
            "",
            "",
            "",
            "Jane Q Example - Talent Lead\nhttps://linkedin.com/in/jane-new",
            "",
        ]
    )
    outcome = await run_apply(db_session, renamed)
    assert (outcome.contacts_added, outcome.contacts_updated) == (0, 1)
    (jane,) = await contacts_of(db_session, "Example Alpha")
    assert jane.name == "Jane Q Example"
    assert jane.name_key == name_key("Jane Q Example")


async def test_US1_AS5_a_blank_field_in_the_file_keeps_what_is_stored(
    db_session: AsyncSession,
) -> None:
    await seeded(db_session)
    await run_apply(
        db_session, sheet(["Example Alpha", "", "", "", "Jane Example - Recruiter [High]", ""])
    )

    outcome = await run_apply(db_session, sheet(["Example Alpha", "", "", "", "Jane Example", ""]))

    assert outcome.contacts_updated == 0
    (jane,) = await contacts_of(db_session, "Example Alpha")
    assert (jane.role, jane.confidence) == ("Recruiter", "high")


async def test_R5_typed_note_is_kept_on_reimport(db_session: AsyncSession) -> None:
    repo = await seeded(db_session)
    alpha = await repo.get_by_key("example-alpha")
    assert alpha is not None
    await NotesRepo(db_session).set(alpha.id, "My own words.", source="typed")

    outcome = await run_apply(db_session, sheet(["Example Alpha", "", "", "", "", "Sheet text"]))

    note = await NotesRepo(db_session).get(alpha.id)
    assert note is not None
    assert (note.body, note.source) == ("My own words.", "typed")
    assert (outcome.notes_kept, outcome.notes_set, outcome.notes_changed) == (1, 0, 0)


async def test_R5_imported_note_is_replaced_when_text_differs(db_session: AsyncSession) -> None:
    repo = await seeded(db_session)
    alpha = await repo.get_by_key("example-alpha")
    assert alpha is not None
    first = await run_apply(db_session, sheet(["Example Alpha", "", "", "", "", "Old text"]))
    assert first.notes_set == 1

    second = await run_apply(db_session, sheet(["Example Alpha", "", "", "", "", "New text"]))

    note = await NotesRepo(db_session).get(alpha.id)
    assert note is not None
    assert (note.body, note.source) == ("New text", "import")
    assert (second.notes_changed, second.notes_set) == (1, 0)


async def test_R5_empty_notes_cell_changes_nothing(db_session: AsyncSession) -> None:
    repo = await seeded(db_session)
    alpha = await repo.get_by_key("example-alpha")
    assert alpha is not None
    await run_apply(db_session, sheet(["Example Alpha", "", "", "", "", "Keep me"]))

    outcome = await run_apply(db_session, sheet(["Example Alpha", "", "", "", "", ""]))

    note = await NotesRepo(db_session).get(alpha.id)
    assert note is not None
    assert note.body == "Keep me"
    assert (outcome.notes_set, outcome.notes_changed, outcome.notes_kept) == (0, 0, 0)


async def test_FR006_import_never_deletes(db_session: AsyncSession) -> None:
    repo = await seeded(db_session)
    alpha = await repo.get_by_key("example-alpha")
    assert alpha is not None
    await ContactsRepo(db_session).add(alpha.id, ContactFields(name="Typed Person"), source="typed")

    await run_apply(db_session, sheet(["Example Alpha", "", "", "", "Jane Example", ""]))

    names = sorted(c.name for c in await contacts_of(db_session, "Example Alpha"))
    assert names == ["Jane Example", "Typed Person"]


async def test_edge_row_fields_that_fail_checks_drop_only_that_field(
    db_session: AsyncSession,
) -> None:
    await seeded(db_session)
    cell = "Jane Example - Recruiter\nemail: not-an-email\nphone: 12"

    outcome = await run_apply(db_session, sheet(["Example Alpha", "", "", "", cell, ""]))

    (jane,) = await contacts_of(db_session, "Example Alpha")
    assert (jane.role, jane.email, jane.phone) == ("Recruiter", None, None)
    reasons = " ".join(s.reason for s in outcome.shortened)
    assert "email" in reasons
    assert "phone" in reasons


async def test_edge_note_over_5000_is_shortened_and_reported(db_session: AsyncSession) -> None:
    repo = await seeded(db_session)

    outcome = await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    zeta = next(c for c in await repo.list_all() if c.name == "Sample Zeta")
    note = await NotesRepo(db_session).get(zeta.id)
    assert note is not None
    assert len(note.body) == 5_000
    assert any("note" in s.reason.lower() for s in outcome.shortened)


async def test_edge_more_than_20_people_is_reported_shortened(db_session: AsyncSession) -> None:
    await seeded(db_session)

    outcome = await run_apply(db_session, SAMPLE.read_text(encoding="utf-8"))

    assert len(await contacts_of(db_session, "Sample Epsilon")) == 20
    assert any("20" in s.reason for s in outcome.shortened)


async def test_preview_writes_nothing_and_matches_the_result(db_session: AsyncSession) -> None:
    await seeded(db_session)
    source = SAMPLE.read_text(encoding="utf-8")

    preview = await run_preview(db_session, source)

    assert await count(db_session, "company_contacts") == 0
    assert await count(db_session, "companies") == 3
    result = await run_apply(db_session, source)
    assert (preview.matched, preview.companies_added, preview.contacts_added) == (
        result.matched,
        result.companies_added,
        result.contacts_added,
    )
    assert (preview.notes_set, len(preview.skipped)) == (result.notes_set, len(result.skipped))
    assert len(preview.rows) == 13  # SC-003: every row is accounted for
    assert result.matched + result.companies_added + len(result.skipped) == 13


async def test_edge_a_company_named_twice_in_the_file_is_added_once(
    db_session: AsyncSession,
) -> None:
    await seeded(db_session)
    source = sheet(
        ["Sample Omega", "Pune", "https://omega.example.test", "", "Ann Example", ""],
        ["Sample Omega Inc", "", "https://omega.example.test", "", "Bob Example", ""],
    )

    preview = await run_preview(db_session, source)
    result = await run_apply(db_session, source)

    assert (preview.companies_added, preview.matched) == (1, 1)
    assert (result.companies_added, result.matched) == (1, 1)
    assert len(await contacts_of(db_session, "Sample Omega")) == 2


async def test_FR004_own_company_gets_a_missing_link_but_a_built_in_one_does_not(
    db_session: AsyncSession,
) -> None:
    repo = await seeded(db_session)
    mine = await repo.add(name="Sample Mine", origin="user", resolution="unresolved")
    beta = await repo.get_by_key("example-beta")
    assert beta is not None
    beta_careers = beta.careers_url

    await run_apply(
        db_session,
        sheet(
            ["Sample Mine", "", "mine.example.test", "https://mine.example.test/jobs", "", ""],
            ["Example Beta", "", "", "https://elsewhere.example.test/careers", "", ""],
        ),
    )

    await db_session.refresh(mine)
    await db_session.refresh(beta)
    assert mine.website == "https://mine.example.test"  # a bare host gets https://
    assert mine.careers_url == "https://mine.example.test/jobs"
    assert beta.careers_url == beta_careers  # shipped facts never change
