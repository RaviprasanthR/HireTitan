"""R7: the LLM port can say "the provider account is out of credit" and carry its message."""

from __future__ import annotations

from hiretitan.platform.llm.port import PAUSE_REASONS, AiUnavailable


def test_R7_out_of_credit_is_a_pause_reason() -> None:
    assert "out_of_credit" in PAUSE_REASONS
    err = AiUnavailable("out_of_credit", provider_message="You exceeded your current quota.")
    assert err.reason == "out_of_credit"
    assert err.provider_message == "You exceeded your current quota."


def test_R7_provider_message_defaults_to_none() -> None:
    assert AiUnavailable("key_missing").provider_message is None


def test_R7_provider_message_capped_at_300() -> None:
    err = AiUnavailable("out_of_credit", provider_message="x" * 1000)
    assert err.provider_message is not None
    assert len(err.provider_message) == 300


def test_R7_provider_message_has_control_characters_stripped() -> None:
    err = AiUnavailable("out_of_credit", provider_message="Out\x00 of\x1b[31m credit\r\n now\t.")
    assert err.provider_message is not None
    assert all(ch.isprintable() or ch == " " for ch in err.provider_message)
    assert "credit" in err.provider_message
