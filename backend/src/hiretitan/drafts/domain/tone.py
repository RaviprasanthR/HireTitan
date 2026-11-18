"""Tone rules for a referral message (spec FR-012, research R4). Pure.

Polite and not pushy is checked in code: an easy way to say no must be there, and no pressure,
guilt, demand or boasting phrase may be.
"""

from __future__ import annotations

import re
from typing import Final

from hiretitan.drafts.domain.checks import Problem

CURLY_APOSTROPHE: Final = chr(0x2019)
DECLINE_PHRASES: Final = (
    "no worries",
    "completely understand",
    "no pressure",
    "if it's not possible",
    "if it is not possible",
    "if you're not comfortable",
    "totally fine",
    "no problem at all",
    "understand if",
)
PRESSURE_PHRASES: Final = (
    "by tomorrow",
    "by end of day",
    "by eod",
    "asap",
    "urgent",
    "right away",
    "i'm counting on you",
    "i am counting on you",
    "you owe",
    "please forward my resume now",
    "you must",
    "you have to",
    "i need you to",
    "i'm the perfect fit",
    "i am the perfect fit",
    "guaranteed",
    "you won't regret",
    "you will not regret",
    "don't ignore",
    "last chance",
)
SUPERLATIVES: Final = re.compile(
    r"\b(?:best|amazing|incredible|brilliant|legendary|awesome|fantastic|greatest|inspiring)\b",
    re.IGNORECASE,
)


def check_tone(body: str, easy_out: str) -> list[Problem]:
    problems: list[Problem] = []
    easy = easy_out.casefold()
    if not easy.strip() or not any(p in easy for p in DECLINE_PHRASES):
        problems.append(
            Problem("easy_out", "Add one sentence that makes it easy for them to say no.")
        )
    whole = f"{body}\n{easy_out}".casefold().replace(CURLY_APOSTROPHE, "'")
    for phrase in PRESSURE_PHRASES:
        if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", whole):
            problems.append(Problem("pressure", f"Remove the pushy phrase '{phrase}'."))
    if len(SUPERLATIVES.findall(whole)) > 1:
        problems.append(Problem("flattery", "Use at most one compliment about them."))
    return problems
