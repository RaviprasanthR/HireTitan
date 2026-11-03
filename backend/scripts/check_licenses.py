"""Licence quality gate for runtime Python dependencies (constitution VIII, R15).

Usage::

    pip-licenses --packages <runtime deps> --from=mixed --format=json > licenses.json
    python scripts/check_licenses.py licenses.json

Allowed: MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0 and LGPL (used unmodified as a
runtime library). SPDX ``AND``/``OR`` expressions and ``;``-joined classifier
lists (alternatives) are understood. ``OVERRIDES`` records reviewed exceptions;
each applies only while the package still reports exactly the reviewed licence.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ALLOWED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"MIT(-0|-CMU)?( License)?",
        r"0BSD|BSD(-[234]-Clause)?( License)?",
        r"Apache(-2\.0| Software License| License,? (Version )?2\.0| 2\.0)?",
        r"ISC( License)?( \(ISCL\))?",
        r"PSF(-2\.0)?|Python Software Foundation License",
        r"MPL-2\.0|Mozilla Public License 2\.0 \(MPL 2\.0\)",
        r"LGPL(v?[23](\.[01])?)?(-only|-or-later|\+)?|LGPL-[23]\.[01](-only|-or-later)?"
        r"|GNU Lesser General Public License.*",
    )
)

# name -> (licence string as reported, why it is acceptable)
OVERRIDES: Mapping[str, tuple[str, str]] = {
    "regex": (
        "Apache-2.0 AND CNRI-Python",
        "CNRI-Python is the permissive, OSI-approved licence of early Python code.",
    ),
    "pypdfium2": (
        "BSD-3-Clause, Apache-2.0, dependency licenses",
        "pypdfium2 is BSD-3-Clause/Apache-2.0; its bundled PDFium is BSD-3-Clause.",
    ),
}

_TOKEN = re.compile(r"\(|\)|\bAND\b|\bOR\b")


def _term_allowed(term: str) -> bool:
    term = term.strip().strip('"').strip()
    return any(p.fullmatch(term) for p in ALLOWED_PATTERNS)


def _tokens(expr: str) -> list[str]:
    out: list[str] = []
    pos = 0
    for m in _TOKEN.finditer(expr):
        if text := expr[pos : m.start()].strip():
            out.append(text)
        out.append(m.group())
        pos = m.end()
    if text := expr[pos:].strip():
        out.append(text)
    return out


def _spdx_allowed(expr: str) -> bool:
    """Evaluate an SPDX-style expression: OR binds looser than AND."""
    tokens = _tokens(expr)
    pos = 0

    def parse_or() -> bool:
        nonlocal pos
        result = parse_and()
        while pos < len(tokens) and tokens[pos] == "OR":
            pos += 1
            rhs = parse_and()
            result = result or rhs
        return result

    def parse_and() -> bool:
        nonlocal pos
        result = parse_atom()
        while pos < len(tokens) and tokens[pos] == "AND":
            pos += 1
            rhs = parse_atom()
            result = result and rhs
        return result

    def parse_atom() -> bool:
        nonlocal pos
        if pos >= len(tokens):
            return False
        item = tokens[pos]
        pos += 1
        if item == "(":
            result = parse_or()
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return result
        return _term_allowed(item)

    allowed = parse_or()
    return allowed and pos == len(tokens)


def is_allowed(license_text: str) -> bool:
    lines = [line.strip() for line in license_text.strip().splitlines() if line.strip()]
    if not lines:
        return False
    # A full licence text pasted into the metadata: judge it by its title line.
    text = lines[0]
    alternatives = [a for a in text.split(";") if a.strip()]
    return any(_term_allowed(a) or _spdx_allowed(a) for a in alternatives)


def evaluate(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return ``"<name> <version>: <licence>"`` for every disallowed package."""
    failures = []
    for row in rows:
        name, version, licence = str(row["Name"]), str(row["Version"]), str(row["License"])
        override = OVERRIDES.get(name.lower())
        if override and override[0] == licence:
            continue
        if not is_allowed(licence):
            failures.append(f"{name} {version}: {licence.splitlines()[0] if licence else ''}")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    rows = json.loads(Path(args[0] if args else "licenses.json").read_text(encoding="utf-8"))
    failures = evaluate(rows)
    for failure in failures:
        print(f"FAIL: disallowed licence: {failure}")
    if not failures:
        print(f"Licence gate passed ({len(rows)} packages).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
