from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from bdgen import secret_store
from bdgen.server.app import create_app

# A 1x1 transparent PNG good enough for any code path that just needs
# bytes-on-disk recognised by PIL or by file-existence checks.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001"
    "0802000000907753de0000000c4944415408d763f8cfc000"
    "0003010100c9fe92ef0000000049454e44ae426082"
)


@pytest.fixture
def make_png() -> Callable[[Path], None]:
    def _write(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG_BYTES)

    return _write


@pytest.fixture
def vault_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("BDGEN_CONFIG_ROOT", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secret_store.lock_vault()
    yield tmp_path
    secret_store.lock_vault()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Boots the FastAPI app against an isolated tmp output root and config root.

    The test client also handles the lifespan, so app.state.jobs is wired up
    to the running event loop just like in production.
    """
    output_root = tmp_path / "output"
    output_root.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    monkeypatch.setenv("BDGEN_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("BDGEN_CONFIG_ROOT", str(config_root))
    monkeypatch.delenv("BDGEN_EXAMPLE_ARCHIVE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secret_store.lock_vault()

    app = create_app(static_dir=None)
    with TestClient(app) as test_client:
        yield test_client
    secret_store.lock_vault()


def make_project_payload(name: str = "demo") -> dict:
    """Minimum-valid BdGenInput payload for the create-project route."""
    return {
        "project": name,
        "metadata": {"title": name.title(), "author": "Tester", "language": "fr"},
        "story": {"synopsis": "Une histoire."},
        "style": {"art_style": "ligne claire"},
        "characters": [
            {"id": "hero", "name": "Hero", "physical_description": "desc"},
        ],
        "structure": {"page_count": 1},
        "generation_options": {
            "script_model": {"provider": "test", "model": "test"},
            "image_model": {"provider": "openai", "model": "gpt-image-2"},
        },
    }
