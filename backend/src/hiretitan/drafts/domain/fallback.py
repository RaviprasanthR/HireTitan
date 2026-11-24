"""Plain templates used when the AI's text cannot be used twice (spec FR-007). Pure.

They are built only from the person's own facts and the job's title and company, so they always
pass the truthfulness checks. They carry the placeholders; the workflow fills the names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from hiretitan.drafts.domain.facts import Fact

CONNECTION_LIMIT: Final = 200
PLACEHOLDER_LEN: Final = len("{recipient_first_name}")


@dataclass(frozen=True, slots=True)
class ReferralParts:
    greeting: str
    body: str
    easy_out: str
    sign_off: str

    def assemble(self) -> str:
        return f"{self.greeting}\n\n{self.body}\n\n{self.easy_out}\n\n{self.sign_off}"


def _top_skill(facts: tuple[Fact, ...] | list[Fact]) -> str | None:
    for fact in facts:
        if fact.kind == "skill":
            return fact.text
    return None


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(limit - 1, 0)].rstrip() + "…"


def connection_fallback(
    role: str, company: str, facts: tuple[Fact, ...] | list[Fact], first_name: str
) -> str:
    """A note of at most 200 characters once ``first_name`` replaces the placeholder."""
    room = CONNECTION_LIMIT - (len(first_name) - PLACEHOLDER_LEN)  # template length that fits
    skill = _top_skill(facts)
    tail = " Would be glad to connect."
    for with_skill in (skill is not None, False):
        lead = f"I work with {skill}, " if with_skill and skill else ""
        for role_max in (60, 40, 25):
            text = (
                f"Hi {{recipient_first_name}}, {lead}I'm interested in the "
                f"{_clip(role, role_max)} role at {_clip(company, 40)}.{tail}"
            )
            if len(text) <= room:
                return text
    return _clip("Hi {recipient_first_name}, I'd be glad to connect.", room)


@dataclass(frozen=True, slots=True)
class EmailParts:
    subject: str
    greeting: str
    body: str
    closing: str


def email_fallback(role: str, company: str, facts: tuple[Fact, ...] | list[Fact]) -> EmailParts:
    skill = _top_skill(facts)
    about = (
        f" I work with {skill}, and I think my experience fits what the team needs."
        if skill
        else ""
    )
    return EmailParts(
        subject=_clip(f"{role} role at {company}", 120),
        greeting="Hi {recipient_first_name},",
        body=(
            f"I'm writing about the {_clip(role, 80)} role at {_clip(company, 60)}.{about} "
            "I'd be glad to share more about my work or talk if that would help."
        ),
        closing="Thank you for your time, and no worries if now is not a good moment.",
    )


def referral_fallback(
    role: str, company: str, facts: tuple[Fact, ...] | list[Fact]
) -> ReferralParts:
    skill = _top_skill(facts)
    about = f" and I work with {skill}" if skill else ""
    return ReferralParts(
        greeting="Hi {recipient_first_name},",
        body=(
            f"I'm interested in the {_clip(role, 80)} role at {_clip(company, 60)}{about}. "
            "If you're open to it, I'd appreciate any advice, or a referral if you think I could "
            "be a fit."
        ),
        easy_out="No pressure at all, and I completely understand if it's not possible.",
        sign_off="Thanks, {my_name}",
    )
