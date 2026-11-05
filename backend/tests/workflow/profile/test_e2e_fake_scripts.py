"""T066: the scripted AI replies used by the Playwright journey are valid and grounded.

The browser run uses ``HIRETITAN_LLM=fake`` with these files. A reply that drops items would
only show up as a confusing UI failure there, so it is checked here first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hiretitan.platform.runtime.domain.run_state import RunStatus

SCRIPTS = Path(__file__).resolve().parents[2] / "fixtures" / "fake_llm" / "e2e"
PDF = "synthetic-mid-2page.pdf"
DOCX_V2 = "synthetic-mid-2page-v2.docx"


def scripted() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((SCRIPTS / "extract_profile.json").read_text("utf-8"))
    return data


@pytest.mark.parametrize(("index", "fixture"), [(0, PDF), (1, DOCX_V2), (2, DOCX_V2)])
async def test_SC001_e2e_script_is_grounded_in_its_resume(
    make_harness: Any, index: int, fixture: str
) -> None:
    h = make_harness([scripted()[index]])
    run_id = await h.start(fixture)

    state = await h.run(run_id)

    assert state.status is RunStatus.awaiting_review
    review = await h.review()
    assert review is not None
    assert review.dropped_items == [], review.dropped_items
    assert review.extraction["contact"]["name"] == "Jane Example"
