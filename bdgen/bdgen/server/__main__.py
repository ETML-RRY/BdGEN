"""Entry point: ``uv run python -m bdgen.server`` to launch the web app.

Set ``BDGEN_OUTPUT_ROOT`` to override where projects are stored. The frontend
build is served from ``bdgen/server/static/`` if it exists; otherwise only the
API is exposed (use the Vite dev server during frontend development).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from bdgen.server.app import create_app


def _static_dir() -> Path | None:
    candidates = [
        Path(__file__).parent / "static",
    ]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "bdgen" / "server" / "static")

    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def main() -> None:
    app = create_app(_static_dir())
    host = os.environ.get("BDGEN_HOST", "127.0.0.1")
    port = int(os.environ.get("BDGEN_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
