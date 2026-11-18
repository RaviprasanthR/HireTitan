"""Read LinkedIn's "Connections.csv" export and match a connection's employer to a company.

The file is the person's own data. It is read here as text and nothing leaves the install.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass

# Words that differ between how a person writes an employer and how a company is listed.
_FILLER = frozenset(
    [
        "inc",
        "ltd",
        "limited",
        "pvt",
        "private",
        "llp",
        "llc",
        "corp",
        "corporation",
        "co",
        "gmbh",
        "plc",
        "india",
        "the",
        "technologies",
        "technology",
        "software",
        "solutions",
        "services",
    ]
)
MAX_ROWS = 20_000


@dataclass(frozen=True, slots=True)
class Connection:
    name: str
    url: str | None
    company: str
    position: str | None


class NotAConnectionsFileError(ValueError):
    pass


def company_match_key(name: str) -> str:
    """The employer's name without case, accents, punctuation, spaces and legal endings."""
    decomposed = unicodedata.normalize("NFKD", name)
    words = "".join(
        ch if ch.isalnum() and not unicodedata.combining(ch) else " " for ch in decomposed
    ).lower()
    kept = [w for w in words.split() if w not in _FILLER]
    return "".join(kept)


@dataclass(frozen=True, slots=True)
class ParsedConnections:
    rows: list[Connection]
    truncated: bool  # the file had more than MAX_ROWS people; the rest were not read


def _is_header(line: str) -> bool:
    first = line.split(",", 1)[0].strip().strip('"').strip()
    return first == "First Name"


def parse_connections(text: str) -> ParsedConnections:
    """The rows of a LinkedIn connections export. LinkedIn puts a few lines of notes first."""
    # split on real line ends only: str.splitlines also splits inside a quoted Position
    lines = text.lstrip(chr(0xFEFF)).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start = next((i for i, line in enumerate(lines) if _is_header(line)), None)
    if start is None:
        raise NotAConnectionsFileError(
            "This does not look like LinkedIn's Connections.csv (no First Name column)."
        )
    header = [cell.strip() for cell in next(csv.reader([lines[start]]))]
    reader = csv.DictReader(io.StringIO("\n".join(lines[start + 1 :])), fieldnames=header)
    found: list[Connection] = []
    truncated = False
    try:
        for row in reader:
            if len(found) >= MAX_ROWS:
                truncated = True
                break
            first = (row.get("First Name") or "").strip()
            last = (row.get("Last Name") or "").strip()
            name = f"{first} {last}".strip()
            company = (row.get("Company") or "").strip()
            if not name or not company:
                continue
            found.append(
                Connection(
                    name=name,
                    url=(row.get("URL") or "").strip() or None,
                    company=company,
                    position=(row.get("Position") or "").strip() or None,
                )
            )
    except csv.Error as error:  # a field over the csv module's limit, a NUL byte
        raise NotAConnectionsFileError(
            f"This file could not be read as a CSV (line {reader.line_num}): {error}."
        ) from error
    return ParsedConnections(found, truncated)
