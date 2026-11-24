"""Build the ``read_job_alert`` request: the email's text and links go inside untrusted blocks.

The AI is shown the email's words and a numbered list of its links, and names a job's link by its
number (FR-013a). Only the first ``LINKS_MAX`` links are listed; ``shown_links`` is the list the
numbers refer to, so a number is always checked against exactly what the AI saw.
"""

from __future__ import annotations

from typing import Final

from hiretitan.mail.domain.mime import Flat, Link
from hiretitan.platform.llm.port import RenderedPrompt
from hiretitan.platform.llm.prompts import LoadedPrompt
from hiretitan.platform.untrusted.delimit import delimit

EMAIL_TEXT_MAX: Final = 12_000
LINKS_MAX: Final = 100
LINK_LINE_MAX: Final = 600
LINK_WORDS_MAX: Final = 80


def shown_links(flat: Flat) -> list[Link]:
    return flat.links[:LINKS_MAX]


def _email_text(flat: Flat) -> str:
    return "\n".join(line.text for line in flat.lines)[:EMAIL_TEXT_MAX]


def _link_line(number: int, link: Link) -> str:
    words = " ".join(link.text.split())[:LINK_WORDS_MAX]
    href = " ".join(link.href.split())  # one line: a link cannot fake another list entry
    line = f"[{number}] {words}: {href}" if words else f"[{number}] {href}"
    return line[:LINK_LINE_MAX]


def render_alert_prompt(prompt: LoadedPrompt, flat: Flat) -> RenderedPrompt:
    links = "\n".join(_link_line(n, link) for n, link in enumerate(shown_links(flat), start=1))
    return prompt.render(
        email_block=delimit("email_text", _email_text(flat)).text,
        links_block=delimit("email_links", links).text,
    )
