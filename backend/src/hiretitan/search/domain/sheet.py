"""Reading a company sheet saved as CSV (feature 002b, FR-001, FR-002, FR-008; research R2).

Pure. The sheet may have empty rows and columns above and beside the data, so the header row is
the first of the first 30 rows with at least two known column names. Only a fixed table of names
is used (no fuzzy matching), so the columns used are predictable and reported back. The openings
columns are recognised only so they can be listed as ignored (FR-008). Every cell has control
characters removed; the cells the importer keeps are capped.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Final

from hiretitan.search.domain.contacts import clean

HEADER_SCAN_ROWS: Final = 30
NAME_MAX: Final = 120
CITY_MAX: Final = 80
URL_MAX: Final = 500
NOTES_MAX: Final = 5_000

# canonical column -> accepted headers, already normalised (see ``_normalise``)
ALIASES: Final = {
    "name": ("org name", "company", "company name", "name"),
    "location": ("location", "locations", "city"),
    "website": ("company site", "website", "site", "url"),
    "careers": ("careers page", "careers", "careers url"),
    "contacts": ("hr linkedin contacts", "linkedin contacts", "contacts"),
    "notes": ("notes", "note"),
}
OPENINGS_HEADERS: Final = (
    "frontend openings",
    "front end openings",
    "backend openings",
    "back end openings",
    "qa openings",
)
_LOOKUP: Final = {alias: column for column, names in ALIASES.items() for alias in names}
_KNOWN: Final = frozenset(_LOOKUP) | frozenset(OPENINGS_HEADERS)
_FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")
_NON_WORD: Final = re.compile(r"[^a-z0-9]+")


class SheetError(ValueError):
    """The file is not a company sheet. ``headers`` are the column names that were seen."""

    def __init__(self, message: str, headers: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.headers = headers


@dataclass(frozen=True, slots=True)
class SheetLayout:
    header_line: int
    used: tuple[str, ...]
    ignored: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SheetRow:
    line: int
    name: str | None
    city: str | None
    website: str | None
    careers_url: str | None
    contacts_cell: str | None
    notes_cell: str | None
    notes_shortened: bool = False


def _normalise(header: str) -> str:
    return _NON_WORD.sub(" ", header.lower()).strip()


def _cell(row: list[str], index: int | None, limit: int) -> tuple[str | None, bool]:
    if index is None or index >= len(row):
        return None, False
    text = clean(row[index])
    if text is None:
        return None, False
    if text.startswith("'") and text[1:2] in _FORMULA_START:  # an export wrote it (FR-021)
        text = text[1:]
    return text[:limit], len(text) > limit


def read(text: str) -> tuple[SheetLayout, list[SheetRow]]:
    """Find the header and return the layout and every non-empty data row.

    Raises ``SheetError`` (with the headers seen) when there is no company-name column.
    """
    records = list(csv.reader(io.StringIO(text.removeprefix("﻿"), newline="")))
    scan = records[:HEADER_SCAN_ROWS]
    header_index = next(
        (
            i
            for i, record in enumerate(scan)
            if sum(_normalise(cell) in _KNOWN for cell in record) >= 2
        ),
        None,
    )
    if header_index is None:
        first = next((r for r in scan if any(c.strip() for c in r)), [])
        raise SheetError("No column with a company name was found.", _headers(first))

    header = records[header_index]
    columns: dict[str, int] = {}
    ignored: list[str] = []
    for index, cell in enumerate(header):
        if not cell.strip():
            continue
        column = _LOOKUP.get(_normalise(cell))
        if column is not None and column not in columns:
            columns[column] = index
        else:
            ignored.append(cell.strip())
    if "name" not in columns:
        raise SheetError("No column with a company name was found.", _headers(header))

    layout = SheetLayout(
        header_index + 1, tuple(c for c in ALIASES if c in columns), tuple(ignored)
    )
    rows: list[SheetRow] = []
    for offset, record in enumerate(records[header_index + 1 :], start=header_index + 2):
        if not any(c.strip() for c in record):
            continue
        name, _ = _cell(record, columns["name"], NAME_MAX)
        city, _ = _cell(record, columns.get("location"), CITY_MAX)
        website, _ = _cell(record, columns.get("website"), URL_MAX)
        careers, _ = _cell(record, columns.get("careers"), URL_MAX)
        contacts, _ = _cell(record, columns.get("contacts"), NOTES_MAX * 6)
        notes, shortened = _cell(record, columns.get("notes"), NOTES_MAX)
        rows.append(SheetRow(offset, name, city, website, careers, contacts, notes, shortened))
    return layout, rows


def _headers(record: list[str]) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in record if cell.strip())
