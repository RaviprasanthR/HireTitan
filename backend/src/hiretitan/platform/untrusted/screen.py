"""Screen untrusted text for prompt-injection attempts (constitution III, FR-006, research R7).

A small, explainable, versioned rule list: each rule has an id, a pattern and a severity.
A *high* signal in the visible text pauses the profile workflow for the user's decision;
medium and low signals are shown on the review screen. Hidden text is screened too but never
pauses the run, because it is already excluded from the AI input.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

RULES_VERSION: Final = 1
EXCERPT_CHARS: Final = 200
MIN_BASE64_DISTINCT: Final = 16

Severity = Literal["high", "medium", "low"]
Location = Literal["visible", "hidden"]

_I = re.IGNORECASE | re.MULTILINE


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    severity: Severity
    pattern: re.Pattern[str]
    accept: Callable[[str], bool] = lambda _match: True  # extra check on the matched text


@dataclass(frozen=True, slots=True)
class Flag:
    rule_id: str
    severity: Severity
    excerpt: str
    location: Location


_TARGET = (
    r"(?:(?:all|any|every|the)\s+)?(?:of\s+)?"
    r"(?:(?:their|the candidate'?s?|his|her|your|this person'?s?)\s+)?"
)

RULES: Final[tuple[Rule, ...]] = (
    # ---- high -------------------------------------------------------------------------------
    Rule(
        "ai_instruction",
        "high",
        re.compile(
            r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+|your\s+)*"
            r"(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|prompts?|rules?)\b"
            r"|\byou\s+are\s+now\s+(?:a|an|the)\b"
            r"|\b(?:reveal|show|print|repeat|output)\s+(?:your\s+)?system\s+prompt\b"
            r"|\bsystem\s+prompt\b"
            r"|\bas\s+an\s+ai\s+(?:language\s+model|assistant)\b",
            _I,
        ),
    ),
    Rule(
        "role_markup",
        "high",
        re.compile(
            r"<\|[a-z_]+\|>|<<\s*/?sys\s*>>|\[/?inst\]|^#{2,}\s*(?:system|assistant|user)\b"
            r"|^\s*(?:system|assistant)\s*:",
            _I,
        ),
    ),
    Rule(
        "tool_call",
        "high",
        re.compile(
            r"<\s*/?(?:tool_call|function_call|tool_use)\b"
            r"|[\"'](?:tool_calls?|function_call)[\"']\s*:"
            r"|\b(?:call|invoke|run|use)\s+the\s+(?:\w+\s+)?(?:tool|function)\b",
            _I,
        ),
    ),
    Rule(
        "output_links",
        "high",
        re.compile(
            rf"\b(?:output|return|include|list|print|provide|give|send|reveal)\s+(?:me\s+)?{_TARGET}"
            r"(?:links?|urls?|e-?mail(?:\s+addresses)?|emails?|phone\s+numbers?|"
            r"contact\s+(?:details|information|data|info))\b",
            _I,
        ),
    ),
    # ---- medium -----------------------------------------------------------------------------
    Rule(
        "reader_manipulation",
        "medium",
        re.compile(
            r"\brate\s+this\s+(?:candidate|resume|applicant|cv)\b"
            r"|\brank\s+(?:me|this\s+(?:resume|candidate|applicant|cv))\s+"
            r"(?:first|highest|top|number\s+one|#1)\b"
            r"|\b(?:hire|select|shortlist)\s+this\s+(?:candidate|applicant)\b",
            _I,
        ),
    ),
    Rule(
        "base64_blob",
        "medium",
        re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"),
        # Real base64 uses many different characters; a long run of one letter is not it.
        accept=lambda match: len(set(match)) >= MIN_BASE64_DISTINCT,
    ),
    # ---- low --------------------------------------------------------------------------------
    Rule("repetition", "low", re.compile(r"\b(\w{2,})\b(?:\s+\1\b){19,}", _I)),
)


def _excerpt(text: str, start: int, end: int) -> str:
    """Up to 200 characters centred on the match."""
    middle = (start + end) // 2
    left = max(0, min(start, middle - EXCERPT_CHARS // 2))
    snippet = text[left : left + EXCERPT_CHARS]
    return " ".join(snippet.split())


def screen(text: str, location: Location = "visible") -> list[Flag]:
    """Every rule that matches, once each, with an excerpt of its first match."""
    flags: list[Flag] = []
    for rule in RULES:
        match = next((m for m in rule.pattern.finditer(text) if rule.accept(m.group(0))), None)
        if match:
            flags.append(
                Flag(rule.id, rule.severity, _excerpt(text, match.start(), match.end()), location)
            )
    return flags
