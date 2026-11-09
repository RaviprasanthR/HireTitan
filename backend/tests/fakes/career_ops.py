"""A scripted ``CareerOpsPort`` for tests: no Node, no network."""

from __future__ import annotations

from uuid import UUID

from hiretitan.search.application.ports import (
    BoardRef,
    CompanyScan,
    DiscoveryResult,
    ScanOk,
    ScanResult,
)


class FakeCareerOps:
    """Answers each company with what the test scripted for it, and records every call."""

    def __init__(self) -> None:
        self._scripted: dict[UUID, CompanyScan] = {}
        self._discoveries: dict[str, DiscoveryResult] = {}
        self.scan_calls: list[list[BoardRef]] = []
        self.discover_calls: list[str] = []

    def script(self, ref: BoardRef, result: CompanyScan) -> None:
        self._scripted[ref.company_id] = result

    def script_discovery(self, careers_url: str, result: DiscoveryResult) -> None:
        self._discoveries[careers_url] = result

    async def scan(self, refs: list[BoardRef]) -> ScanResult:
        self.scan_calls.append(list(refs))
        return {ref.company_id: self._scripted.get(ref.company_id, ScanOk([])) for ref in refs}

    async def discover(self, careers_url: str) -> DiscoveryResult | None:
        self.discover_calls.append(careers_url)
        return self._discoveries.get(careers_url)
