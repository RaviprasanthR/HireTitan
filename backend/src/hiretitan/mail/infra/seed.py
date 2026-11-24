"""Read the shipped sender list, failing fast on a bad file (FR-010)."""

from __future__ import annotations

from pathlib import Path

import yaml

from hiretitan.mail.domain.senders import SeedSender, SenderError, parse_seed


def load_seed(path: Path) -> tuple[SeedSender, ...]:
    try:
        raw = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SenderError(f"Could not read the sender list: {error}") from error
    return parse_seed(raw)
