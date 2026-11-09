"""T016: the shipped company list is loaded without overwriting what the person changed (FR-018)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.application.seed import SeedError, load_seed
from hiretitan.search.infra.repos import CompaniesRepo

FIXTURES = Path(__file__).parents[2] / "fixtures" / "companies"
V1 = FIXTURES / "seed_v1.yaml"
V2 = FIXTURES / "seed_v2.yaml"
NOW = datetime(2026, 11, 5, tzinfo=UTC)


async def by_key(session: AsyncSession, key: str):  # type: ignore[no-untyped-def]
    row = await CompaniesRepo(session).get_by_key(key)
    assert row is not None, key
    await session.refresh(row)
    return row


async def test_FR018_new_seed_rows_inserted(db_session: AsyncSession) -> None:
    first = await load_seed(CompaniesRepo(db_session), V1)
    assert (first.inserted, first.updated) == (3, 0)

    second = await load_seed(CompaniesRepo(db_session), V2)

    assert second.inserted == 1  # Delta
    assert (await by_key(db_session, "example-delta")).name == "Example Delta"
    alpha = await by_key(db_session, "example-alpha")
    assert (alpha.city, alpha.board_id, alpha.seed_version) == ("Hyderabad", "examplealpha2", 2)
    assert (await by_key(db_session, "example-gamma")).name == "Example Gamma"  # left alone
    assert alpha.origin == "built_in"


async def test_loading_twice_changes_nothing(db_session: AsyncSession) -> None:
    await load_seed(CompaniesRepo(db_session), V2)
    again = await load_seed(CompaniesRepo(db_session), V2)
    assert (again.inserted, again.updated) == (0, 0)


async def test_FR018_user_modified_rows_not_overwritten(db_session: AsyncSession) -> None:
    await load_seed(CompaniesRepo(db_session), V1)
    repo = CompaniesRepo(db_session)
    alpha = await by_key(db_session, "example-alpha")
    await repo.set_fields(alpha.id, city="Kochi", user_modified=True)

    await load_seed(CompaniesRepo(db_session), V2)

    alpha = await by_key(db_session, "example-alpha")
    assert (alpha.city, alpha.board_id) == ("Kochi", "examplealpha")  # the person's edit wins


async def test_FR018_hidden_rows_stay_hidden(db_session: AsyncSession) -> None:
    await load_seed(CompaniesRepo(db_session), V1)
    alpha = await by_key(db_session, "example-alpha")
    await CompaniesRepo(db_session).set_fields(alpha.id, hidden=True)

    await load_seed(CompaniesRepo(db_session), V2)

    alpha = await by_key(db_session, "example-alpha")
    assert alpha.hidden is True
    assert alpha.board_id == "examplealpha"  # not touched either


async def test_FR018_deleted_built_in_row_not_reinserted(db_session: AsyncSession) -> None:
    await load_seed(CompaniesRepo(db_session), V1)
    alpha = await by_key(db_session, "example-alpha")
    await CompaniesRepo(db_session).set_fields(alpha.id, deleted_at=NOW)

    result = await load_seed(CompaniesRepo(db_session), V2)

    assert result.inserted == 1  # only Delta
    alpha = await by_key(db_session, "example-alpha")
    assert alpha.deleted_at == NOW
    assert alpha.board_id == "examplealpha"
    keys = [c.key for c in await CompaniesRepo(db_session).list_all() if c.key == "example-alpha"]
    assert keys == []  # still deleted, so not listed, and still one row


@pytest.mark.parametrize("extra", ["hr_email", "hr_name", "notes", "phone", "linkedin"])
async def test_FR015_seed_with_contact_fields_is_rejected(
    db_session: AsyncSession, tmp_path: Path, extra: str
) -> None:
    rows = yaml.safe_load(V1.read_text("utf-8"))
    rows[0][extra] = "someone@example.test"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(rows), "utf-8")

    with pytest.raises(SeedError) as caught:
        await load_seed(CompaniesRepo(db_session), path)

    assert extra in str(caught.value)
    assert await CompaniesRepo(db_session).get_by_key("example-alpha") is None  # nothing loaded


@pytest.mark.parametrize(
    "change",
    [
        {"key": ""},
        {"name": ""},
        {"resolution": "guess"},
        {"ats_vendor": "greenhouse", "board_id": None},
        {"seed_version": "one"},
    ],
)
async def test_invalid_rows_are_rejected_before_anything_is_written(
    db_session: AsyncSession, tmp_path: Path, change: dict[str, object]
) -> None:
    rows = yaml.safe_load(V1.read_text("utf-8"))
    rows[1].update(change)
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(rows), "utf-8")

    with pytest.raises(SeedError):
        await load_seed(CompaniesRepo(db_session), path)

    assert await CompaniesRepo(db_session).get_by_key("example-alpha") is None


async def test_duplicate_keys_in_a_file_are_rejected(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    rows = yaml.safe_load(V1.read_text("utf-8"))
    rows.append(dict(rows[0]))
    path = tmp_path / "dup.yaml"
    path.write_text(yaml.safe_dump(rows), "utf-8")

    with pytest.raises(SeedError, match="example-alpha"):
        await load_seed(CompaniesRepo(db_session), path)
