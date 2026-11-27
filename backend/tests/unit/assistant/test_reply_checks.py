"""002m T005: checks on Mikasa's reply before it is shown and stored (research R9)."""

from __future__ import annotations

from hiretitan.assistant.domain.reply_checks import MIKASA_TEXT_MAX, check_reply

JOB = "job:0190a1b2-0000-7000-8000-000000000001"
OTHER = "job:0190a1b2-0000-7000-8000-0000000000ff"
ROUTES = ("/", "/explore", "/jobs/:id", "/settings", "/settings/:tab", "/profile")


def test_R9_known_refs_kept() -> None:
    checked = check_reply(f"You applied to [[{JOB}]].", known_refs={JOB}, routes=ROUTES)
    assert checked.text == f"You applied to [[{JOB}]]."
    assert checked.removed_refs == []
    assert checked.refs == [JOB]


def test_R9_unknown_ref_removed() -> None:
    checked = check_reply(f"See [[{OTHER}]] and [[{JOB}]].", known_refs={JOB}, routes=ROUTES)
    assert OTHER not in checked.text
    assert f"[[{JOB}]]" in checked.text
    assert checked.removed_refs == [OTHER]
    assert "  " not in checked.text


def test_R9_bad_link_removed() -> None:
    text = "Open [[page:/settings/gmail]] or [[page:/admin/secret]] or [[page:/jobs/abc]]."
    checked = check_reply(text, known_refs=set(), routes=ROUTES)
    assert "[[page:/settings/gmail]]" in checked.text
    assert "[[page:/jobs/abc]]" in checked.text
    assert "/admin/secret" not in checked.text
    assert checked.removed_links == ["/admin/secret"]


def test_R9_reply_capped() -> None:
    checked = check_reply("x" * (MIKASA_TEXT_MAX + 50), known_refs=set(), routes=ROUTES)
    assert len(checked.text) == MIKASA_TEXT_MAX
    assert checked.truncated is True
