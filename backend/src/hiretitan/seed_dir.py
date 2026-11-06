"""Where the shipped seed files (companies, title synonyms) live.

In a source checkout they sit next to `src/`. In the Docker image the package is installed into
site-packages, so the image sets `HIRETITAN_SEED_DIR` to the copied folder instead.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

CHECKOUT_SEED_DIR: Final = Path(__file__).resolve().parents[2] / "seed"


def resolve_seed_dir(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get("HIRETITAN_SEED_DIR", "").strip()
    return Path(configured) if configured else CHECKOUT_SEED_DIR
