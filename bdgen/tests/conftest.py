from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

import pytest

from bdgen import secret_store

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
