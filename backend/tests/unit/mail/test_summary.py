"""What a check found adds up (T039): SC-008, FR-012."""

from __future__ import annotations

import pytest

from hiretitan.mail.application.ports import SinkCounts
from hiretitan.mail.workflow.check import MESSAGES_MAX
from hiretitan.search.application.alerts import AlertCounts


@pytest.mark.parametrize(
    ("new", "known", "left_out", "pipeline"),
    [(0, 0, 0, 0), (5, 0, 0, 0), (3, 2, 4, 1), (0, 9, 0, 9)],
)
def test_SC008_counts_add_up(new: int, known: int, left_out: int, pipeline: int) -> None:
    sink = SinkCounts(new=new, already_known=known, left_out=left_out, already_in_pipeline=pipeline)
    alert = AlertCounts(
        new=new, already_known=known, left_out=left_out, already_in_pipeline=pipeline
    )

    assert sink.found == alert.found == new + known + left_out + pipeline


def test_FR012_200_cap_is_the_documented_one() -> None:
    assert MESSAGES_MAX == 200
