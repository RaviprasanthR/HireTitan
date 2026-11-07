"""Company list as a CSV file: export, and import with a preview (US3 AS6, research R11).

Header ``name,city,website,careers_url,ats_vendor,board_id,hidden``. An import never changes
anything by itself: ``plan_import`` compares the file with the stored companies and returns what
would be added or updated, plus the rows that cannot be used and why; ``apply_import`` makes those
changes once the person confirms. A company is the same one when the names match (ignoring case)
and the careers-page hosts match, or one of the two has no careers link. An empty cell leaves the
stored value alone, so a partial sheet never wipes data; an export imports back with no changes.
Cells that a spreadsheet would run as a formula are written with a leading apostrophe and read
back without it.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Final, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from hiretitan.search.application.companies import (
    CompaniesStore,
    CompanyError,
    StoredCompany,
    check_fields,
)

COLUMNS: Final = ("name", "city", "website", "careers_url", "ats_vendor", "board_id", "hidden")
MAX_BYTES: Final = 1_048_576
MAX_ROWS: Final = 2000
BOARD_ID_MAX: Final = 200
_VENDOR: Final = re.compile(r"[a-z][a-z0-9_]{0,39}")
_FORMULA_START: Final = ("=", "+", "-", "@")
_TRUE: Final = frozenset({"true", "yes", "1", "y"})
_FALSE: Final = frozenset({"false", "no", "0", "n"})
_COMPARED: Final = ("name", "city", "website", "careers_url", "ats_vendor", "board_id", "hidden")


class CsvFileError(ValueError):
    """The whole file is refused. ``status`` is the HTTP status that describes why."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class ImportRow:
    line: int
    name: str
    city: str | None = None
    website: str | None = None
    careers_url: str | None = None
    ats_vendor: str | None = None
    board_id: str | None = None
    hidden: bool | None = None  # None: the cell was empty, leave it as it is


@dataclass(frozen=True, slots=True)
class InvalidRow:
    line: int
    reason: str


@dataclass(frozen=True, slots=True)
class Change:
    before: Any
    after: Any


@dataclass(frozen=True, slots=True)
class UpdateRow:
    line: int
    company_id: UUID
    name: str
    changes: dict[str, Change]


@dataclass(frozen=True, slots=True)
class ImportPlan:
    add: list[ImportRow] = field(default_factory=list)
    update: list[UpdateRow] = field(default_factory=list)
    invalid: list[InvalidRow] = field(default_factory=list)


class ImportStore(CompaniesStore, Protocol):
    async def list_all(self) -> list[Any]: ...

    async def add(self, **fields: Any) -> Any: ...


# ---- export ----------------------------------------------------------------------------------
def _safe(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def _unsafe(text: str) -> str:
    return text[1:] if text.startswith("'") and text[1:2] in _FORMULA_START else text


def export_csv(rows: list[StoredCompany]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [
                _safe(row.name),
                _safe(row.city),
                _safe(row.website),
                _safe(row.careers_url),
                _safe(row.ats_vendor),
                _safe(row.board_id),
                "true" if row.hidden else "false",
            ]
        )
    return out.getvalue()


# ---- reading the file ------------------------------------------------------------------------
def _host(url: str | None) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.") if url else ""


def _row_of(line: int, cells: dict[str, str]) -> ImportRow:
    """Check one row; raises ``CompanyError`` with what is wrong."""
    text = {name: _unsafe((cells.get(name) or "").strip()) for name in COLUMNS}
    values = check_fields({k: text[k] for k in ("name", "city", "website", "careers_url")})
    vendor, board = text["ats_vendor"].lower(), text["board_id"]
    problems: list[str] = []
    if vendor and not _VENDOR.fullmatch(vendor):
        problems.append("The board provider must be a short lowercase name such as lever.")
    if bool(vendor) != bool(board):
        problems.append("A board needs both ats_vendor and board_id.")
    elif len(board) > BOARD_ID_MAX or any(ch.isspace() for ch in board):
        problems.append("The board id is too long or has spaces in it.")
    hidden: bool | None = None
    flag = text["hidden"].lower()
    if flag in _TRUE:
        hidden = True
    elif flag in _FALSE:
        hidden = False
    elif flag:
        problems.append("hidden must be true or false.")
    if problems:
        raise ValueError(" ".join(problems))
    return ImportRow(
        line,
        values["name"],
        values.get("city"),
        values.get("website"),
        values.get("careers_url"),
        vendor or None,
        board or None,
        hidden,
    )


def parse_csv(data: bytes) -> tuple[list[ImportRow], list[InvalidRow]]:
    if len(data) > MAX_BYTES:
        raise CsvFileError(413, "The file is larger than 1 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CsvFileError(422, "This is not a text (CSV) file.") from error
    if "\x00" in text:
        raise CsvFileError(422, "This is not a text (CSV) file.")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    if "name" not in header:
        raise CsvFileError(422, "The first row must have a column called name.")
    reader.fieldnames = header
    rows: list[ImportRow] = []
    invalid: list[InvalidRow] = []
    seen = 0
    for cells in reader:
        line = reader.line_num
        if not any((v or "").strip() for v in cells.values() if isinstance(v, str)):
            continue  # a blank line
        seen += 1
        if seen > MAX_ROWS:
            raise CsvFileError(422, "The file has more than 2,000 rows.")
        try:
            rows.append(_row_of(line, {k: v for k, v in cells.items() if isinstance(v, str)}))
        except CompanyError as error:
            invalid.append(InvalidRow(line, " ".join(e.message for e in error.errors)))
        except ValueError as error:
            invalid.append(InvalidRow(line, str(error)))
    return rows, invalid


class _Named(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def careers_url(self) -> str | None: ...


# ---- comparing with the stored list ----------------------------------------------------------
def _find[T: _Named](row: ImportRow, stored: list[T]) -> T | None:
    host = _host(row.careers_url)
    for company in stored:
        if company.name.casefold() != row.name.casefold():
            continue
        other = _host(company.careers_url)
        if not host or not other or host == other:
            return company
    return None


def _changes(row: ImportRow, company: StoredCompany) -> dict[str, Change]:
    found: dict[str, Change] = {}
    for name in _COMPARED:
        new = getattr(row, name)
        if new is None:
            continue
        old = getattr(company, name)
        if name == "name":
            if old != new and old.casefold() == new.casefold():
                found[name] = Change(old, new)
            continue
        if old != new:
            found[name] = Change(old, new)
    return found


def plan_import(
    rows: list[ImportRow], invalid: list[InvalidRow], stored: list[StoredCompany]
) -> ImportPlan:
    plan = ImportPlan(invalid=list(invalid))
    taken: list[ImportRow] = []
    for row in rows:
        if _find(row, taken) is not None:
            plan.invalid.append(InvalidRow(row.line, "This company is already in the file."))
            continue
        taken.append(row)
        company = _find(row, stored)
        if company is None:
            plan.add.append(row)
        elif changes := _changes(row, company):
            plan.update.append(UpdateRow(row.line, company.id, company.name, changes))
    plan.invalid.sort(key=lambda r: r.line)
    return plan


# ---- applying --------------------------------------------------------------------------------
async def preview_import(store: ImportStore, data: bytes) -> tuple[ImportPlan, list[ImportRow]]:
    rows, invalid = parse_csv(data)
    return plan_import(rows, invalid, list(await store.list_all())), rows


async def apply_import(store: ImportStore, rows: list[ImportRow]) -> tuple[int, int]:
    """Make the changes for ``rows`` against the list as it is now; returns (added, updated)."""
    plan = plan_import(rows, [], list(await store.list_all()))
    for row in plan.add:
        board = row.ats_vendor and row.board_id
        fields: dict[str, Any] = {
            "origin": "user",
            "name": row.name,
            "city": row.city,
            "website": row.website,
            "careers_url": row.careers_url,
            "ats_vendor": row.ats_vendor,
            "board_id": row.board_id,
            "hidden": bool(row.hidden),
            "resolution": (
                "user_confirmed" if board else "careers_page" if row.careers_url else "unresolved"
            ),
        }
        await store.add(**fields)
    for update in plan.update:
        values = {name: change.after for name, change in update.changes.items()}
        if "ats_vendor" in values or "board_id" in values:
            values["resolution"] = "user_confirmed"
        if set(values) - {"hidden"}:
            values["user_modified"] = True
        await store.set_fields(update.company_id, **values)
    return len(plan.add), len(plan.update)
