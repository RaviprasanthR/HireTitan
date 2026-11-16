"""A scripted ``DescriptionPort``: the text of each posting by its link, and a record of reads."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from hiretitan.search.application.ports import DescribeRequest, DescriptionResult


@dataclass
class FakeDescriptions:
    # link -> text; a link that is not here cannot be read
    texts: dict[str, str] = field(default_factory=dict)
    calls: list[DescribeRequest] = field(default_factory=list)
    on_read: Callable[[DescribeRequest], Awaitable[None]] | None = None  # a side effect per read

    async def read(self, job: DescribeRequest) -> DescriptionResult:
        self.calls.append(job)
        if self.on_read is not None:
            await self.on_read(job)
        text = self.texts.get(job.url)
        if text is None:
            return DescriptionResult("unreadable", error="not found")
        return DescriptionResult("read", text)

    def urls(self) -> list[str]:
        return [call.url for call in self.calls]
