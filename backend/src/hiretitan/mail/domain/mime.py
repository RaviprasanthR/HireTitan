"""Turn one email into plain lines and links, and nothing else (feature 002c, FR-013, FR-014, R4).

Only the standard library: ``email`` (``policy.default``) and ``html.parser``. The HTML part is
preferred, else the text part. Text a person cannot see (``display:none``, ``font-size:0``, ...) is
set aside in ``hidden``: it never becomes a job, but the prompt-injection screen still looks at it.
Control, zero-width and bidirectional characters are removed. Nothing is fetched or followed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from html.parser import HTMLParser
from typing import Final, Literal

MAX_RAW_BYTES: Final = 2 * 1024 * 1024  # R13: an alert is far smaller than this
MAX_LINES: Final = 5000
MAX_LINE_CHARS: Final = 1000
MAX_LINKS: Final = 500
MAX_HIDDEN: Final = 50
MAX_DEPTH: Final = 100  # alert emails nest tables a dozen deep; more is hostile or broken
MAX_TAGS: Final = 100_000
HREF_MAX: Final = 2000

_REMOVED: Final = frozenset({"Cc", "Cf"})
_URL: Final = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_HIDDEN_STYLE: Final = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all|opacity\s*:\s*0(?![\d.])"
    # a font under 2 px is not for reading; 1.2em or 100% are ordinary sizes
    r"|font-size\s*:\s*(?:0+(?:\.\d+)?|1(?:\.\d+)?|0?\.\d+)\s*(?:px|pt)?\s*(?:[;!]|$)"
    r"|font-size\s*:\s*0+(?:\.\d+)?\s*(?:em|rem|%)\s*(?:[;!]|$)"
    r"|max-height\s*:\s*0(?![\d.])|(?:left|top|text-indent)\s*:\s*-\d{4,}",
    re.IGNORECASE,
)
_COLOR_STYLE: Final = re.compile(r"(?<![-\w])color\s*:", re.IGNORECASE)
_VOID: Final = frozenset({"br", "hr", "img", "meta", "link", "input", "wbr"})
_SKIPPED: Final = frozenset({"script", "style", "head", "title"})
_MUTED_TAGS: Final = frozenset({"small", "i", "em"})
# these start a new line when they open or close
_BLOCKS: Final = frozenset(
    {
        "p", "div", "br", "tr", "td", "th", "li", "ul", "ol", "table", "tbody", "thead", "h1",
        "h2", "h3", "h4", "h5", "h6", "hr", "section", "article", "header", "footer",
        "blockquote", "pre", "dl", "dt", "dd", "center", "body", "html",
    }
)  # fmt: skip
# an opening one of these closes an unclosed one of the same kind (``<p>a<p>b``)
_SELF_CLOSING: Final = frozenset({"p", "li", "td", "th", "tr", "dt", "dd"})


def _href_ok(href: str) -> bool:
    """A link as the email gave it, with nothing a database or a screen cannot take: no control,
    zero-width or bidirectional character, no space, not absurdly long."""
    return len(href) <= HREF_MAX and all(
        not ch.isspace() and unicodedata.category(ch) not in _REMOVED for ch in href
    )


class UnreadableMessageError(Exception):
    """The email is too large or cannot be read at all (counted as "could not read", FR-017)."""


@dataclass(frozen=True, slots=True)
class Line:
    text: str
    muted: bool = (
        False  # small print, italics, coloured text: skills, tags, "be an early applicant"
    )


@dataclass(frozen=True, slots=True)
class Link:
    text: str  # the visible words of the link ("" for a bare address in a text part)
    href: str  # as the email gave it, never followed
    line: int  # index in ``Flat.lines`` of the line the link sits on


@dataclass(frozen=True, slots=True)
class Flat:
    source: Literal["html", "text", "none"]
    lines: list[Line] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)


def clean(text: str) -> str:
    """NFKC, no control, zero-width or bidirectional characters, one space between words."""
    normal = unicodedata.normalize("NFKC", text)
    kept = "".join(
        " " if ch in "\n\t\r\f\v" else ch
        for ch in normal
        if ch in "\n\t\r\f\v" or unicodedata.category(ch) not in _REMOVED
    )
    return " ".join(kept.split())


class _Flattener(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[Line] = []
        self.links: list[Link] = []
        self.hidden: list[str] = []
        self._stack: list[tuple[str, bool, bool]] = []  # (tag, hides text, mutes text)
        # running counts, so the checks below do not scan the stack for every piece of text
        self._hidden_n = 0
        self._skipped_n = 0
        self._muted_n = 0
        self._tags = 0
        self._pieces: list[str] = []
        self._line_muted = True
        self._hidden_pieces: list[str] = []
        self._anchor: tuple[str, int] | None = None
        self._anchor_pieces: list[str] = []

    # ---- state -----------------------------------------------------------------------------
    @property
    def _is_hidden(self) -> bool:
        return self._hidden_n > 0

    @property
    def _is_skipped(self) -> bool:
        return self._skipped_n > 0

    @property
    def _is_muted(self) -> bool:
        return self._muted_n > 0

    def _flush_line(self) -> None:
        text = clean("".join(self._pieces))
        muted = self._line_muted
        self._pieces = []
        self._line_muted = True
        if not text or len(self.lines) >= MAX_LINES:
            return
        self.lines.append(Line(text[:MAX_LINE_CHARS], muted))

    def _flush_hidden(self) -> None:
        text = clean("".join(self._hidden_pieces))
        self._hidden_pieces = []
        if text and len(self.hidden) < MAX_HIDDEN:
            self.hidden.append(text)

    # ---- parser callbacks --------------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCKS:
            self._flush_line()
        if tag in _VOID:
            return
        self._tags += 1
        if self._tags > MAX_TAGS or len(self._stack) >= MAX_DEPTH:
            raise UnreadableMessageError("The email's layout is too deep or too large to read.")
        if tag in _SELF_CLOSING and any(entry[0] == tag for entry in self._stack):
            self._close(tag)
        values = {name: (value or "") for name, value in attrs}
        style = values.get("style", "")
        hides = (
            bool(_HIDDEN_STYLE.search(style))
            or "hidden" in values
            or values.get("aria-hidden", "").lower() == "true"
        )
        mutes = tag in _MUTED_TAGS or (tag != "a" and bool(_COLOR_STYLE.search(style)))
        self._stack.append((tag, hides, mutes))
        self._hidden_n += hides
        self._skipped_n += tag in _SKIPPED
        self._muted_n += mutes
        if tag == "a" and not self._is_hidden and self._anchor is None:
            href = values.get("href", "").strip()
            if (
                href.lower().startswith(("http://", "https://"))
                and _href_ok(href)
                and len(self.links) < MAX_LINKS
            ):
                self._anchor = (href, len(self.lines))
                self._anchor_pieces = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKS:
            self._flush_line()
        self._close(tag)

    def handle_data(self, data: str) -> None:
        if self._is_skipped:
            return
        if self._is_hidden:
            self._hidden_pieces.append(data)
            return
        if not data.strip():
            self._pieces.append(" ")
            return
        self._pieces.append(data)
        if not self._is_muted:
            self._line_muted = False
        if self._anchor is not None:
            self._anchor_pieces.append(data)

    def _close(self, tag: str) -> None:
        index = next(
            (i for i in range(len(self._stack) - 1, -1, -1) if self._stack[i][0] == tag), None
        )
        if index is None:
            return
        was_hidden = self._is_hidden
        if tag == "a" and self._anchor is not None:
            self._finish_anchor()
        for tag_name, hides, mutes in self._stack[index:]:
            self._hidden_n -= hides
            self._skipped_n -= tag_name in _SKIPPED
            self._muted_n -= mutes
        del self._stack[index:]
        if was_hidden and not self._is_hidden:
            self._flush_hidden()

    def _finish_anchor(self) -> None:
        if self._anchor is None:
            return
        href, line = self._anchor
        self._anchor = None
        words = clean("".join(self._anchor_pieces))
        if words:
            self.links.append(Link(words[:MAX_LINE_CHARS], href, line))

    def finish(self) -> None:
        self.close()
        self._flush_line()
        self._flush_hidden()


def _flatten_html(html: str) -> Flat:
    parser = _Flattener()
    parser.feed(html)
    parser.finish()
    return Flat("html", parser.lines, parser.links, parser.hidden)


def _flatten_text(text: str) -> Flat:
    lines: list[Line] = []
    links: list[Link] = []
    for raw_line in text.splitlines():
        line = clean(raw_line)
        if not line or len(lines) >= MAX_LINES:
            continue
        for match in _URL.finditer(raw_line):  # on the raw line: cleaning must not mend an address
            if len(links) < MAX_LINKS and _href_ok(match.group(0)):
                links.append(Link("", match.group(0), len(lines)))
        lines.append(Line(line[:MAX_LINE_CHARS]))
    return Flat("text", lines, links)


def _content(part: EmailMessage) -> str:
    try:
        return str(part.get_content())
    except (LookupError, ValueError, UnicodeError):  # an unknown or wrong charset
        payload = part.get_payload(decode=True)
        return payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else ""


def flatten_message(raw: bytes) -> Flat:
    """The lines and links of one email. ``UnreadableMessageError`` when it is over 2 MB."""
    if len(raw) > MAX_RAW_BYTES:
        raise UnreadableMessageError("The email is larger than 2 MB.")
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        body = message.get_body(preferencelist=("html", "plain"))
    except (
        Exception
    ) as error:  # the parser is lenient, but a hostile message must not crash a check
        raise UnreadableMessageError("The email could not be parsed.") from error
    if body is None or not isinstance(body, EmailMessage):
        return Flat("none")
    content = _content(body)
    return (
        _flatten_html(content) if body.get_content_type() == "text/html" else _flatten_text(content)
    )
