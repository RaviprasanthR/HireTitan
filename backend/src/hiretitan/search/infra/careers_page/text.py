"""Turn a careers page into the plain text the AI reads (T053). Pure: it gets text, not a request.

Only what a visitor sees is kept (no scripts, styles or hidden templates). A link is written next
to its text as ``Backend Engineer <https://host/jobs/1>``, because a page's job titles are often
plain text beside an "Apply" link and the model has to give back the link. The result is cleaned
like any untrusted text and cut to 20,000 characters.
"""

from __future__ import annotations

import contextlib
import re
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urljoin, urlsplit

from hiretitan.platform.untrusted.sanitize import sanitize

PAGE_TEXT_MAX: Final = 20_000
_LINK: Final = re.compile(r"<(https?://[^<>\s]+)>")

_BLOCKS: Final = frozenset(
    {
        "p", "br", "li", "ul", "ol", "div", "tr", "td", "th", "table", "section", "article",
        "header", "footer", "nav", "main", "h1", "h2", "h3", "h4", "h5", "h6",
    }
)  # fmt: skip
_HIDDEN: Final = frozenset({"script", "style", "noscript", "template", "svg"})


class _Text(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._page_url = page_url
        self._hidden = 0
        self._href: str | None = None
        self.out: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN:
            self._hidden += 1
        elif tag in _BLOCKS:
            self.out.append("\n")
        elif tag == "a":
            self._href = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN:
            self._hidden = max(0, self._hidden - 1)
        elif tag in _BLOCKS:
            self.out.append("\n")
        elif tag == "a" and self._href is not None:
            href = self._href.strip()
            target = urljoin(self._page_url, href)
            if not href.startswith("#") and urlsplit(target).scheme in ("http", "https"):
                self.out.append(f" <{target}>")
            self._href = None

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self.out.append(data)


def page_links(text: str) -> frozenset[str]:
    """The links written into ``page_text`` output: the only ones the AI may give back."""
    return frozenset(_LINK.findall(text))


def page_text(html: str, page_url: str) -> str:
    reader = _Text(page_url)
    with contextlib.suppress(Exception):  # a page the parser cannot read gives what it had
        reader.feed(html)
    with contextlib.suppress(Exception):
        reader.close()
    cleaned = sanitize("".join(reader.out)).text
    lines = (re.sub(r"[ \t\f\v]+", " ", line).strip() for line in cleaned.split("\n"))
    return "\n".join(line for line in lines if line)[:PAGE_TEXT_MAX]
