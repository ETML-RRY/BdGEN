"""Entry point: ``uv run python -m bdgen.server`` to launch the web app.

Set ``BDGEN_OUTPUT_ROOT`` to override where projects are stored. The frontend
build is served from ``bdgen/server/static/`` if it exists; otherwise only the
API is exposed (use the Vite dev server during frontend development).
"""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from .app import create_app


def main() -> None:
    static_dir = Path(__file__).parent / "static"
    app = create_app(static_dir if static_dir.exists() else None)
    host = os.environ.get("BDGEN_HOST", "127.0.0.1")
    port = int(os.environ.get("BDGEN_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
