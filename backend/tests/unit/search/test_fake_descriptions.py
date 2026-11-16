"""002i T013: the file-based description reader used by the end-to-end stack."""

from __future__ import annotations

import json
from pathlib import Path

from hiretitan.search.application.ports import DescribeRequest
from hiretitan.search.infra.descriptions.fake import FileDescriptions


async def test_a_listed_link_is_read_and_others_are_not(tmp_path: Path) -> None:
    (tmp_path / "descriptions.json").write_text(
        json.dumps({"https://jobs.example.com/a": "Build Python APIs."}), "utf-8"
    )
    reader = FileDescriptions(tmp_path)

    found = await reader.read(DescribeRequest("https://jobs.example.com/a"))
    missing = await reader.read(DescribeRequest("https://jobs.example.com/b"))

    assert (found.status, found.text) == ("read", "Build Python APIs.")
    assert missing.status == "unreadable"


async def test_no_folder_or_a_broken_file_reads_nothing(tmp_path: Path) -> None:
    assert (await FileDescriptions(None).read(DescribeRequest("https://x.example/a"))).status == (
        "unreadable"
    )
    (tmp_path / "descriptions.json").write_text("{broken", "utf-8")
    broken = await FileDescriptions(tmp_path).read(DescribeRequest("https://x.example/a"))
    assert broken.status == "unreadable"
