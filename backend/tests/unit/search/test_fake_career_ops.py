"""T012: the career-ops port and its scripted fake."""

from __future__ import annotations

from uuid import uuid4

from tests.fakes.career_ops import FakeCareerOps

from hiretitan.search.application.ports import (
    BoardRef,
    DiscoveryResult,
    Posting,
    ScanError,
    ScanOk,
)


def posting(title: str = "Backend Engineer") -> Posting:
    return Posting(title=title, url=f"https://jobs.example.test/{title.replace(' ', '-')}")


async def test_fake_returns_scripted_results_per_company() -> None:
    good, bad, unscripted = (
        BoardRef(uuid4(), "greenhouse", "a"),
        BoardRef(uuid4(), "lever", "b"),
        BoardRef(uuid4(), "ashby", "c"),
    )
    fake = FakeCareerOps()
    fake.script(good, ScanOk([posting("One"), posting("Two")]))
    fake.script(bad, ScanError("The board did not answer."))

    result = await fake.scan([good, bad, unscripted])

    assert result[good.company_id] == ScanOk([posting("One"), posting("Two")])
    assert result[bad.company_id] == ScanError("The board did not answer.")
    assert result[unscripted.company_id] == ScanOk([])  # nothing scripted means no jobs


async def test_fake_records_calls() -> None:
    ref = BoardRef(uuid4(), "workday", "x")
    fake = FakeCareerOps()

    await fake.scan([ref])
    await fake.scan([ref, ref])

    assert [len(call) for call in fake.scan_calls] == [1, 2]


async def test_fake_discovery() -> None:
    fake = FakeCareerOps()
    found = DiscoveryResult(vendor="lever", board_id="acme")
    fake.script_discovery("https://careers.example.test", found)

    assert await fake.discover("https://careers.example.test") == found
    assert await fake.discover("https://other.example.test") is None
    assert fake.discover_calls == ["https://careers.example.test", "https://other.example.test"]
