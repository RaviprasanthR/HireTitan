"""Registry of every module that defines ORM tables on ``Base.metadata``.

Alembic's env and the model/migration drift test import these so the metadata
is complete. Feature modules register here too: this function lives in
platform but imports feature models lazily (by name), so the platform package
itself never depends on a feature module at import time.
"""

from __future__ import annotations

import importlib

MODEL_MODULES: tuple[str, ...] = (
    "hiretitan.platform.runtime.infra.models",
    "hiretitan.platform.llm.infra.models",
)


def import_all_models() -> None:
    for name in MODEL_MODULES:
        importlib.import_module(name)
