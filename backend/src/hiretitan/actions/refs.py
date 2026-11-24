"""Refs: how the model names an item (``job:<uuid>``), and labels for private items (R5).

A label is built only from non-private fields (a company name, a job title), so the model can
talk about "a contact at Acme" without ever seeing the contact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from uuid import UUID

REF_KINDS: Final = frozenset(
    {
        "job",
        "company",
        "contact",
        "note",
        "interview",
        "round",
        "question",
        "resume_file",
        "draft",
        "tailored_resume",
        "search_run",
        "sender",
        "duplicate",
        "review_item",
    }
)
_REF = re.compile(r"^([a-z_]+):([0-9a-fA-F-]{36})$")


@dataclass(frozen=True, slots=True)
class Ref:
    kind: str
    id: UUID

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"

    @classmethod
    def parse(cls, text: str, *, expect: str | None = None) -> Ref:
        match = _REF.match(text.strip())
        if match is None or match.group(1) not in REF_KINDS:
            raise ValueError(f"Not a ref: {text!r}")
        if expect is not None and match.group(1) != expect:
            raise ValueError(f"Expected a {expect} ref, got {text!r}")
        try:
            return cls(match.group(1), UUID(match.group(2)))
        except ValueError:
            raise ValueError(f"Not a ref: {text!r}") from None


def label_contact(company: str) -> str:
    return f"a contact at {company}"


def label_note(company: str) -> str:
    return f"your note on {company}"


def label_interview(title: str, company: str) -> str:
    return f"the interview details for {title} at {company}"


def label_round(title: str, company: str) -> str:
    return f"an interview round for {title} at {company}"


def label_question(title: str, company: str) -> str:
    return f"an interview question for {title} at {company}"


def label_resume_file() -> str:
    return "one of your resume files"
