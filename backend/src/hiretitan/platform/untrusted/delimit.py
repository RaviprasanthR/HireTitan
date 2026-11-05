"""Wrap untrusted text in a data block (architecture §6).

The boundary is a random 16-byte hex token chosen per block. If the token happens to
appear in the text, another is drawn, so the text can never close its own block.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from hiretitan.platform.llm.port import UntrustedText


def _new_token() -> str:
    return secrets.token_hex(16)


def delimit(
    label: str, text: str, *, token_factory: Callable[[], str] = _new_token
) -> UntrustedText:
    token = token_factory()
    while token in text:
        token = token_factory()
    block = f"<<DATA {token} label={label}>>\n{text}\n<<END {token}>>"
    return UntrustedText(label=label, text=block)
