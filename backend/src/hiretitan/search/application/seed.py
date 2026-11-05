"""Load the shipped company list into the database (research R10, FR-015, FR-018).

The file holds company-level facts only. The loader rejects any field it does not know, so a
contact name, an email or a note can never ride in with a release (constitution VIII). It inserts
companies it has not seen and updates only built-in rows the person never edited, hid or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from hiretitan.search.application.ports import CompanyStore
from hiretitan.search.domain.companies import RESOLUTIONS

ALLOWED_FIELDS: Final = frozenset(
    {
        "key",
        "name",
        "city",
        "website",
        "careers_url",
        "ats_vendor",
        "board_id",
        "resolution",
        "seed_version",
    }
)
REQUIRED_FIELDS: Final = ("key", "name", "resolution", "seed_version")
# what an update may change; the key and the person's own flags are never written
UPDATABLE_FIELDS: Final = tuple(sorted(ALLOWED_FIELDS - {"key"}))


class SeedError(ValueError):
    """The seed file is not acceptable. Nothing is written."""


@dataclass(frozen=True, slots=True)
class SeedResult:
    inserted: int
    updated: int
    skipped: int  # rows the person changed, hid or deleted, or that were already up to date


def read_seed(path: Path) -> list[dict[str, Any]]:
    """Parse and check the whole file before anything touches the database."""
    try:
        rows = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SeedError(f"Could not read the company list: {error}") from error
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise SeedError("The company list must be a list of companies.")
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        _check_row(index, row)
        if row["key"] in seen:
            raise SeedError(f"The key {row['key']!r} appears twice.")
        seen.add(row["key"])
    return rows


def _check_row(index: int, row: dict[str, Any]) -> None:
    unknown = sorted(set(row) - ALLOWED_FIELDS)
    if unknown:
        raise SeedError(
            f"Company {index}: unknown field(s) {', '.join(unknown)}. "
            "The list holds company facts only, never contacts or notes."
        )
    for name in REQUIRED_FIELDS:
        if row.get(name) in (None, ""):
            raise SeedError(f"Company {index}: {name} is required.")
    if not isinstance(row["seed_version"], int) or isinstance(row["seed_version"], bool):
        raise SeedError(f"Company {index}: seed_version must be a whole number.")
    if row["resolution"] not in RESOLUTIONS:
        raise SeedError(f"Company {index}: resolution {row['resolution']!r} is not allowed.")
    if row.get("ats_vendor") and not row.get("board_id"):
        raise SeedError(f"Company {index}: a job-board provider needs a board id.")


async def load_seed(store: CompanyStore, path: Path) -> SeedResult:
    rows = read_seed(path)
    inserted = updated = skipped = 0
    for row in rows:
        values = {name: row.get(name) for name in UPDATABLE_FIELDS}
        existing = await store.get_by_key(row["key"])
        if existing is None:
            await store.add(key=row["key"], origin="built_in", **values)
            inserted += 1
            continue
        editable = (
            existing.origin == "built_in"
            and not existing.user_modified
            and not existing.hidden
            and existing.deleted_at is None
        )
        if not editable or all(getattr(existing, name) == value for name, value in values.items()):
            skipped += 1
            continue
        await store.set_fields(existing.id, **values)
        updated += 1
    return SeedResult(inserted, updated, skipped)
