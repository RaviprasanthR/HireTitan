"""Write the backend's OpenAPI schema as JSON (input to `npm run gen:api`).

Usage: python scripts/export_openapi.py [output.json]   (default: print to stdout)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings


def main(argv: list[str]) -> int:
    # Settings are only read to build the app; no database connection is made.
    schema = create_app(Settings(), frontend_dist=Path("/nonexistent")).openapi()
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if len(argv) > 1:
        Path(argv[1]).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
