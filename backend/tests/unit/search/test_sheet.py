"""Reading a company sheet saved as CSV (feature 002b, T008; FR-001, FR-002, FR-008)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.search.domain.sheet import SheetError, read

FIXTURES = Path(__file__).parents[2] / "fixtures" / "sheets"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_FR002_header_found_below_empty_rows_and_columns() -> None:
    layout, rows = read(_fixture("product_companies_sample.csv"))

    assert layout.header_line == 6
    assert set(layout.used) == {"name", "location", "website", "careers", "contacts", "notes"}
    assert len(rows) == 13
    first = rows[0]
    assert first.line == 7
    assert first.name == "Example Alpha"
    assert first.city == "Pune"
    assert first.website == "https://www.alpha.example.test/"
    assert first.careers_url is None
    assert first.contacts_cell is not None
    assert first.contacts_cell.startswith("Jane Example - Recruiter [High]")
    assert first.notes_cell == "Referred by a friend"


def test_FR002_unknown_columns_are_reported_ignored() -> None:
    text = "Company,City,Favourite colour,Budget\nAcme,Pune,blue,10\n"

    layout, rows = read(text)

    assert layout.used == ("name", "location")
    assert layout.ignored == ("Favourite colour", "Budget")
    assert rows[0].name == "Acme"


def test_FR008_openings_columns_are_ignored() -> None:
    layout, rows = read(_fixture("product_companies_sample.csv"))

    assert "Frontend openings" in layout.ignored
    assert "Backend openings" in layout.ignored
    assert not hasattr(rows[0], "frontend_openings")


def test_002_export_columns_without_a_meaning_here_are_ignored() -> None:
    text = "name,city,website,careers_url,ats_vendor,board_id,hidden\nAcme,Pune,,,,,\n"

    layout, _ = read(text)

    assert set(layout.used) == {"name", "location", "website", "careers"}
    assert layout.ignored == ("ats_vendor", "board_id", "hidden")


def test_FR001_no_name_column_refuses_the_file() -> None:
    with pytest.raises(SheetError) as caught:
        read(_fixture("not_a_sheet.csv"))

    assert caught.value.headers == ("Project", "Owner", "Budget")


def test_FR001_header_without_a_name_column_refuses_the_file() -> None:
    with pytest.raises(SheetError) as caught:
        read("Contacts,Notes\nJane,hello\n")

    assert caught.value.headers == ("Contacts", "Notes")


def test_FR001_empty_file_refuses() -> None:
    with pytest.raises(SheetError) as caught:
        read("\n\n,,\n")

    assert caught.value.headers == ()


def test_FR001_bom_and_crlf_are_handled() -> None:
    text = "﻿Org Name,Location\r\nAcme,Pune\r\nBeta,Chennai\r\n"

    layout, rows = read(text)

    assert layout.header_line == 1
    assert [r.name for r in rows] == ["Acme", "Beta"]
    assert [r.city for r in rows] == ["Pune", "Chennai"]


def test_edge_header_search_stops_after_30_rows() -> None:
    lines = ["," * 3] * 30 + ["Company,City", "Acme,Pune"]
    with pytest.raises(SheetError):
        read("\n".join(lines) + "\n")

    ok_lines = ["," * 3] * 29 + ["Company,City", "Acme,Pune"]
    layout, rows = read("\n".join(ok_lines) + "\n")
    assert layout.header_line == 30
    assert rows[0].name == "Acme"


def test_FR002_empty_rows_between_data_are_skipped_and_line_numbers_kept() -> None:
    layout, rows = read("Company,City\nAcme,\n\n,\nBeta,\n")

    assert layout.header_line == 1
    assert [(r.line, r.name) for r in rows] == [(2, "Acme"), (5, "Beta")]


def test_edge_row_without_a_name_is_kept_with_no_name() -> None:
    _, rows = read("Company,City\n,Pune\n")

    assert rows[0].name is None
    assert rows[0].city == "Pune"


def test_FR026_control_characters_are_stripped_from_every_cell() -> None:
    _, rows = read("Company,Contacts\nAc\x00me​,Jane\x07 Example\n")

    assert rows[0].name == "Acme"
    assert rows[0].contacts_cell == "Jane Example"


def test_edge_cells_are_capped() -> None:
    long_note = "n" * 6_000
    cells = [f"{'x' * 200}", f"{'c' * 200}", f"https://{'w' * 600}.example", long_note]
    text = "Company,City,Website,Notes\n" + ",".join(cells) + "\n"

    _, rows = read(text)

    row = rows[0]
    assert row.name is not None
    assert len(row.name) == 120
    assert row.city is not None
    assert len(row.city) == 80
    assert row.website is not None
    assert len(row.website) == 500
    assert row.notes_cell is not None
    assert len(row.notes_cell) == 5_000
    assert row.notes_shortened is True


def test_edge_short_note_is_not_flagged_shortened() -> None:
    _, rows = read("Company,Notes\nAcme,fine\n")

    assert rows[0].notes_shortened is False


def test_FR002_first_column_of_a_kind_wins() -> None:
    layout, rows = read("Company,Notes,Notes\nAcme,first,second\n")

    assert rows[0].notes_cell == "first"
    assert layout.ignored == ("Notes",)


def test_FR002_headers_ignore_case_spacing_and_punctuation() -> None:
    layout, rows = read(
        " ORG  NAME ,careers_url,HR / LinkedIn Contacts\nAcme,https://a.example,Jane\n"
    )

    assert set(layout.used) == {"name", "careers", "contacts"}
    assert rows[0].careers_url == "https://a.example"
    assert rows[0].contacts_cell == "Jane"
