"""Importing a company sheet: preview it, then apply it (feature 002b; FR-001 to FR-008).

One code path serves both. ``preview_sheet`` runs it without writing, ``apply_sheet`` runs the
same rows and writes, so the preview counts are the counts the person gets (SC-002). The caller
owns the transaction: a failed apply writes nothing.

* A built-in company's facts never change (FR-004); an own company may get a missing website or
  careers link filled in.
* A company that is not on the list is added as the person's own and stays unresolved.
* A contact is the same person when the name key matches, or when the LinkedIn link matches and
  the name changed (research R4). Blank cells never erase what is stored, and an import never
  removes a contact or a note (FR-006).
* A note the person typed is kept; an imported note is replaced only when its text differs (R5).
* Contacts and notes are the person's own data and are never sent to an AI (FR-022).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from hiretitan.search.application.companies import CompanyError, check_fields
from hiretitan.search.application.contacts import ContactsStore, NotesStore, StoredContact
from hiretitan.search.application.discovery import add_company_from_import
from hiretitan.search.domain.company_match import (
    Ambiguous,
    CompanyRef,
    Matched,
    NoMatch,
    match,
)
from hiretitan.search.domain.contacts import (
    COMPANY_NOTE_MAX,
    ContactFields,
    check_contact,
    link_key,
    name_key,
)
from hiretitan.search.domain.contacts_cell import ParsedContact, parse
from hiretitan.search.domain.sheet import SheetLayout, SheetRow

NoteAction = Literal["set", "changed", "kept", "none"]
RowAction = Literal["matched", "add", "skip"]


class SheetCompaniesStore(Protocol):
    async def list_filtered(self, filter: str) -> list[Any]: ...

    async def add(self, **fields: Any) -> Any: ...

    async def set_fields(self, company_id: UUID, **fields: Any) -> None: ...


@dataclass(frozen=True, slots=True)
class RowIssue:
    line: int
    reason: str


@dataclass(frozen=True, slots=True)
class RowOutcome:
    line: int
    company: str
    action: RowAction
    contacts_add: int = 0
    contacts_update: int = 0
    note: NoteAction = "none"
    shortened: bool = False


@dataclass(frozen=True, slots=True)
class SheetOutcome:
    """What a preview would do, or what an apply did (``SheetPreview`` and ``SheetResult``)."""

    layout: SheetLayout
    rows: tuple[RowOutcome, ...]
    skipped: tuple[RowIssue, ...]
    shortened: tuple[RowIssue, ...]

    @property
    def matched(self) -> int:
        return sum(r.action == "matched" for r in self.rows)

    @property
    def companies_added(self) -> int:
        return sum(r.action == "add" for r in self.rows)

    @property
    def contacts_added(self) -> int:
        return sum(r.contacts_add for r in self.rows)

    @property
    def contacts_updated(self) -> int:
        return sum(r.contacts_update for r in self.rows)

    @property
    def notes_set(self) -> int:
        return sum(r.note == "set" for r in self.rows)

    @property
    def notes_changed(self) -> int:
        return sum(r.note == "changed" for r in self.rows)

    @property
    def notes_kept(self) -> int:
        return sum(r.note == "kept" for r in self.rows)


@dataclass(slots=True)
class _Known:
    """A contact as the run sees it: the stored one, or one this run already added."""

    id: UUID | None
    fields: ContactFields
    source: str


def _fields_of(row: StoredContact) -> ContactFields:
    return ContactFields(
        name=row.name,
        role=row.role,
        linkedin_url=row.linkedin_url,
        email=row.email,
        phone=row.phone,
        confidence=row.confidence,
        note=row.note,
    )


def _merge(old: ContactFields, new: ContactFields) -> ContactFields:
    """The new facts win where the file has them; a blank never erases a stored value."""
    same_person = name_key(old.name) == name_key(new.name)
    return ContactFields(
        name=old.name if same_person else new.name,
        role=new.role or old.role,
        linkedin_url=new.linkedin_url or old.linkedin_url,
        email=new.email or old.email,
        phone=new.phone or old.phone,
        confidence=new.confidence or old.confidence,
        note=new.note or old.note,
    )


def _as_web_link(text: str | None) -> str | None:
    if not text:
        return None
    return text if "://" in text else f"https://{text}"


class _Run:
    """The state of one import: the companies, and what this run has added so far."""

    def __init__(
        self,
        companies: SheetCompaniesStore,
        contacts: ContactsStore,
        notes: NotesStore,
        *,
        write: bool,
    ) -> None:
        self.companies = companies
        self.contacts = contacts
        self.notes = notes
        self.write = write
        self.rows: dict[UUID, Any] = {}
        self.refs: list[CompanyRef] = []
        self.real: set[UUID] = set()
        self.by_name: dict[tuple[UUID, str], _Known | None] = {}
        self.by_link: dict[tuple[UUID, str], _Known | None] = {}
        self.note_state: dict[UUID, tuple[str, str] | None] = {}

    async def load(self) -> None:
        for row in await self.companies.list_filtered("all"):
            self.rows[row.id] = row
            self.real.add(row.id)
            self.refs.append(CompanyRef(row.id, row.name, row.website))

    # -- companies -------------------------------------------------------------------------

    async def add_company(self, row: SheetRow, name: str) -> tuple[UUID, list[str]]:
        """Add the row's company as the person's own; a bad optional field is dropped."""
        values = {
            "name": name,
            "city": row.city,
            "website": _as_web_link(row.website),
            "careers_url": _as_web_link(row.careers_url),
        }
        dropped: list[str] = []
        try:
            check_fields({k: v or "" for k, v in values.items()})
        except CompanyError as error:
            for issue in error.errors:
                values[issue.field] = None
                dropped.append(issue.field)
        if self.write:
            view = await add_company_from_import(
                self.companies,  # type: ignore[arg-type]
                name=name,
                careers_url=values["careers_url"],
                city=values["city"],
                website=values["website"],
            )
            company_id = view.id
            self.real.add(company_id)
        else:
            company_id = uuid4()
        self.rows[company_id] = _Planned(name, values["website"], values["careers_url"])
        self.refs.append(CompanyRef(company_id, name, values["website"]))
        return company_id, dropped

    async def fill_missing(self, company_id: UUID, row: SheetRow) -> None:
        """An own company may get the website or careers link it is missing (FR-004)."""
        company = self.rows[company_id]
        if getattr(company, "origin", "user") != "user":
            return
        changes: dict[str, str] = {}
        for field, value in (("website", row.website), ("careers_url", row.careers_url)):
            link = _as_web_link(value)
            if link and not getattr(company, field, None):
                try:
                    check_fields({field: link})
                except CompanyError:
                    continue
                changes[field] = link
        if changes and self.write and company_id in self.real:
            await self.companies.set_fields(company_id, **changes)

    # -- contacts --------------------------------------------------------------------------

    async def known_by_name(self, company_id: UUID, key: str) -> _Known | None:
        slot = (company_id, key)
        if slot not in self.by_name:
            found = (
                await self.contacts.find_by_name_key(company_id, key)
                if company_id in self.real
                else None
            )
            self.by_name[slot] = (
                _Known(found.id, _fields_of(found), found.source) if found else None
            )
        return self.by_name[slot]

    async def known_by_link(self, company_id: UUID, key: str | None) -> _Known | None:
        if key is None:
            return None
        slot = (company_id, key)
        if slot not in self.by_link:
            found = (
                await self.contacts.find_by_link_key(company_id, key)
                if company_id in self.real
                else None
            )
            self.by_link[slot] = (
                _Known(found.id, _fields_of(found), found.source) if found else None
            )
        return self.by_link[slot]

    async def put_contact(
        self, company_id: UUID, fields: ContactFields
    ) -> Literal["add", "update", "same"]:
        key = name_key(fields.name)
        known = await self.known_by_name(company_id, key)
        if known is None:
            known = await self.known_by_link(company_id, link_key(fields.linkedin_url))
        if known is None:
            row_id: UUID | None = None
            if self.write:
                row_id = (await self.contacts.add(company_id, fields, source="import")).id
            self._remember(company_id, _Known(row_id, fields, "import"))
            return "add"
        merged = _merge(known.fields, fields)
        if merged == known.fields:
            return "same"
        if self.write and known.id is not None:
            await self.contacts.update(known.id, merged)
        self.by_name.pop((company_id, name_key(known.fields.name)), None)
        self._remember(company_id, replace(known, fields=merged))
        return "update"

    def _remember(self, company_id: UUID, known: _Known) -> None:
        self.by_name[(company_id, name_key(known.fields.name))] = known
        lk = link_key(known.fields.linkedin_url)
        if lk is not None:
            self.by_link[(company_id, lk)] = known

    # -- notes -----------------------------------------------------------------------------

    async def put_note(self, company_id: UUID, body: str) -> NoteAction:
        if company_id not in self.note_state:
            stored = await self.notes.get(company_id) if company_id in self.real else None
            self.note_state[company_id] = (stored.body, stored.source) if stored else None
        current = self.note_state[company_id]
        if current is None:
            action: NoteAction = "set"
        elif current[0] == body:
            return "none"
        elif current[1] == "typed":
            return "kept"  # the person's own words are not overwritten (R5)
        else:
            action = "changed"
        if self.write:
            await self.notes.set(company_id, body, source="import")
        self.note_state[company_id] = (body, "import")
        return action


@dataclass(frozen=True, slots=True)
class _Planned:
    """A company this run is adding (preview only has no stored row for it)."""

    name: str
    website: str | None
    careers_url: str | None
    origin: str = "user"


def _checked_contact(parsed: ParsedContact) -> tuple[ContactFields | None, list[str]]:
    """Check an imported contact; a bad optional field is dropped, not the whole person."""
    args: dict[str, str | None] = {
        "name": parsed.name,
        "role": parsed.role,
        "linkedin_url": parsed.linkedin_url,
        "email": parsed.email,
        "phone": parsed.phone,
        "confidence": parsed.confidence,
        "note": parsed.note,
    }
    fields, issues = check_contact(**args)
    if fields is not None:
        return fields, []
    bad = {issue.field for issue in issues}
    if "name" in bad:
        return None, ["name"]
    for field in bad:
        args[field] = None
    fields, _ = check_contact(**args)
    return fields, sorted(bad)


def _note_body(row: SheetRow, leftover: tuple[str, ...]) -> tuple[str | None, bool]:
    parts = [p for p in (row.notes_cell, *leftover) if p]
    if not parts:
        return None, False
    body = "\n".join(parts)
    if len(body) > COMPANY_NOTE_MAX:
        return body[:COMPANY_NOTE_MAX], True
    return body, row.notes_shortened


async def _run(run: _Run, layout: SheetLayout, rows: list[SheetRow]) -> SheetOutcome:
    await run.load()
    outcomes: list[RowOutcome] = []
    skipped: list[RowIssue] = []
    shortened: list[RowIssue] = []
    for row in rows:
        if row.name is None:
            skipped.append(RowIssue(row.line, "The row has no company name."))
            outcomes.append(RowOutcome(row.line, "", "skip"))
            continue
        result = match(row.name, _as_web_link(row.website), run.refs)
        if isinstance(result, Ambiguous):
            reason = "The row matches two companies: " + ", ".join(result.names) + "."
            skipped.append(RowIssue(row.line, reason))
            outcomes.append(RowOutcome(row.line, row.name, "skip"))
            continue
        if isinstance(result, Matched):
            company_id, action = result.company_id, "matched"
            await run.fill_missing(company_id, row)
        else:
            assert isinstance(result, NoMatch)
            try:
                company_id, dropped = await run.add_company(row, row.name)
            except CompanyError as error:
                reason = "; ".join(issue.message for issue in error.errors)
                skipped.append(RowIssue(row.line, reason))
                outcomes.append(RowOutcome(row.line, row.name, "skip"))
                continue
            action = "add"
            for field in dropped:
                shortened.append(RowIssue(row.line, f"Dropped an invalid {field} for {row.name}."))

        parsed = parse(row.contacts_cell or "")
        added = updated = 0
        for contact in parsed.contacts:
            fields, bad = _checked_contact(contact)
            for field in bad:
                subject = contact.name if fields is not None else "a contact"
                shortened.append(
                    RowIssue(row.line, f"Dropped an invalid {field} for {subject}.")
                    if fields is not None
                    else RowIssue(row.line, "Skipped a contact with no usable name.")
                )
            if fields is None:
                continue
            outcome = await run.put_contact(company_id, fields)
            added += outcome == "add"
            updated += outcome == "update"
        flagged = parsed.shortened
        if flagged:
            shortened.append(
                RowIssue(row.line, "More than 20 people in the cell; kept the first 20.")
            )
        body, note_cut = _note_body(row, parsed.leftover)
        note: NoteAction = await run.put_note(company_id, body) if body else "none"
        if note_cut:
            shortened.append(
                RowIssue(row.line, f"The note was longer than {COMPANY_NOTE_MAX} characters.")
            )
        outcomes.append(
            RowOutcome(
                row.line,
                row.name,
                action,  # type: ignore[arg-type]
                added,
                updated,
                note,
                flagged or note_cut,
            )
        )
    return SheetOutcome(layout, tuple(outcomes), tuple(skipped), tuple(shortened))


async def preview_sheet(
    companies: SheetCompaniesStore,
    contacts: ContactsStore,
    notes: NotesStore,
    layout: SheetLayout,
    rows: list[SheetRow],
) -> SheetOutcome:
    """What an import would do. Writes nothing."""
    return await _run(_Run(companies, contacts, notes, write=False), layout, rows)


async def apply_sheet(
    companies: SheetCompaniesStore,
    contacts: ContactsStore,
    notes: NotesStore,
    layout: SheetLayout,
    rows: list[SheetRow],
) -> SheetOutcome:
    """Do the import. The caller commits, so a failure part-way saves nothing."""
    return await _run(_Run(companies, contacts, notes, write=True), layout, rows)
