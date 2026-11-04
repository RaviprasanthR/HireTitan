"""Find text in a PDF that a human cannot see (FR-005, research R6).

A character is hidden if its fill colour is within DeltaE < 8 of its background (white,
unless a filled rectangle under it says otherwise), its size is under 4 pt, or its box lies
outside the page. Hidden characters are grouped into runs and removed from the AI input; the
runs are reported to the user and screened for injection, but never pause the run.

Not detected: render mode 3 (invisible text). pdfplumber does not expose it, and the
white / tiny / off-page tricks cover the common attacks (the attack set guards regressions).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from pdfplumber.pdf import PDF

MIN_VISIBLE_SIZE: Final = 4.0
MAX_DELTA_E: Final = 8.0
WHITE: Final = (1.0, 1.0, 1.0)
_LINE_TOLERANCE: Final = 3.0

Char = dict[str, Any]
Rgb = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class HiddenRun:
    page: int  # 1-based
    text: str


@dataclass(frozen=True, slots=True)
class HiddenText:
    visible_chars: list[Char]
    hidden_runs: list[HiddenRun]
    page_count: int


# ---- colour ---------------------------------------------------------------------------------
def _to_rgb(color: Any) -> Rgb | None:
    """pdfplumber colours: None, a number, or a tuple of 1 (grey), 3 (RGB) or 4 (CMYK) numbers."""
    if color is None:
        return None
    values = [float(color)] if isinstance(color, (int, float)) else [float(c) for c in color]
    if len(values) == 1:
        return (values[0], values[0], values[0])
    if len(values) == 3:
        return (values[0], values[1], values[2])
    if len(values) == 4:
        c, m, y, k = values
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def _lab(rgb: Rgb) -> tuple[float, float, float]:
    def linear(v: float) -> float:
        v = min(max(v, 0.0), 1.0)
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(v) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: Rgb, b: Rgb) -> float:
    """CIE76 colour distance."""
    return math.dist(_lab(a), _lab(b))


# ---- detection ------------------------------------------------------------------------------
def _background(char: Char, rects: Sequence[tuple[Rgb, float, float, float, float]]) -> Rgb:
    """The colour of the topmost filled rectangle under the character's centre, else white."""
    cx = (char["x0"] + char["x1"]) / 2
    cy = (char["top"] + char["bottom"]) / 2
    for colour, x0, x1, top, bottom in reversed(rects):
        if x0 <= cx <= x1 and top <= cy <= bottom:
            return colour
    return WHITE


def _filled_rects(page: Any) -> list[tuple[Rgb, float, float, float, float]]:
    out: list[tuple[Rgb, float, float, float, float]] = []
    for rect in page.rects:
        colour = _to_rgb(rect.get("non_stroking_color"))
        if rect.get("fill") and colour is not None:
            out.append((colour, rect["x0"], rect["x1"], rect["top"], rect["bottom"]))
    return out


def _outside(char: Char, bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    return bool(
        char["x1"] <= x0 or char["x0"] >= x1 or char["bottom"] <= top or char["top"] >= bottom
    )


def _hidden_flags(
    chars: Sequence[Char], bbox: tuple[float, float, float, float], rects: Sequence[Any]
) -> list[bool]:
    """Per-character hidden flags. A string that starts off the page stays hidden even where
    its tail wanders back onto the page: the reader sees only a few stray letters."""
    flags: list[bool] = []
    spilling = False
    previous: Char | None = None
    for char in chars:
        off_page = _outside(char, bbox) and not char["text"].isspace()
        adjacent = (
            previous is not None
            and abs(char["top"] - previous["top"]) <= _LINE_TOLERANCE
            and -1.0 <= char["x0"] - previous["x1"] < 1.5 * float(previous.get("size") or 10)
        )
        spilling = off_page or (spilling and adjacent)
        flags.append(spilling or _is_hidden(char, bbox, rects))
        previous = char
    return flags


def _is_hidden(char: Char, bbox: tuple[float, float, float, float], rects: Sequence[Any]) -> bool:
    if char["text"].isspace():
        return False
    if float(char.get("size") or 0) < MIN_VISIBLE_SIZE:
        return True
    if _outside(char, bbox):
        return True
    fill = _to_rgb(char.get("non_stroking_color"))
    if fill is None:
        return False  # no fill colour recorded: default black
    return delta_e(fill, _background(char, rects)) < MAX_DELTA_E


def _runs(page_number: int, chars: list[Char]) -> list[HiddenRun]:
    """Group hidden characters into one run per line, with spaces where the gaps are."""
    runs: list[HiddenRun] = []
    line: list[Char] = []

    def flush() -> None:
        if line:
            runs.append(HiddenRun(page_number, _line_text(line)))
            line.clear()

    for char in chars:
        if line and abs(char["top"] - line[-1]["top"]) > _LINE_TOLERANCE:
            flush()
        line.append(char)
    flush()
    return [run for run in runs if run.text]


def _line_text(chars: list[Char]) -> str:
    out: list[str] = []
    previous: Char | None = None
    for char in chars:
        if previous is not None:
            gap = char["x0"] - previous["x1"]
            if gap > 0.2 * float(previous.get("size") or 10):
                out.append(" ")
        out.append(char["text"])
        previous = char
    return "".join(out).strip()


def detect_hidden(pdf: PDF) -> HiddenText:
    visible: list[Char] = []
    hidden_runs: list[HiddenRun] = []
    for page in pdf.pages:
        rects = _filled_rects(page)
        bbox = (float(page.bbox[0]), float(page.bbox[1]), float(page.bbox[2]), float(page.bbox[3]))
        hidden_on_page: list[Char] = []
        flags = _hidden_flags(page.chars, bbox, rects)
        for char, is_hidden in zip(page.chars, flags, strict=True):
            if is_hidden:
                hidden_on_page.append(char)
            else:
                visible.append({**char, "page_number": page.page_number})
        hidden_runs.extend(_runs(page.page_number, hidden_on_page))
    return HiddenText(visible, hidden_runs, len(pdf.pages))


def visible_text(result: HiddenText) -> str:
    """The visible characters as text: lines in reading order, spaces at gaps."""
    lines: list[list[Char]] = []
    for char in result.visible_chars:
        new_page = lines and lines[-1][-1]["page_number"] != char["page_number"]
        if lines and not new_page and abs(char["top"] - lines[-1][-1]["top"]) <= _LINE_TOLERANCE:
            lines[-1].append(char)
        else:
            lines.append([char])
    return "\n".join(_line_text(line) for line in lines)
