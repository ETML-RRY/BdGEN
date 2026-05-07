from __future__ import annotations

from pathlib import Path

import pytest

from bdgen import secret_store


@pytest.fixture
def vault_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BDGEN_CONFIG_ROOT", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secret_store.lock_vault()
    yield tmp_path
    secret_store.lock_vault()


def test_create_unlock_and_persist_update(vault_root: Path) -> None:
    secret_store.create_vault(
        "correct horse battery staple",
        {"OPENAI_API_KEY": "sk-test"},
    )
    assert (vault_root / secret_store.VAULT_FILENAME).exists()
    assert secret_store.get_secret("OPENAI_API_KEY") == "sk-test"

    secret_store.update_secret("OPENAI_API_KEY", "sk-new")
    secret_store.lock_vault()
    assert secret_store.get_secret("OPENAI_API_KEY") is None

    secret_store.unlock_vault("correct horse battery staple")
    assert secret_store.get_secret("OPENAI_API_KEY") == "sk-new"


def test_wrong_password_fails(vault_root: Path) -> None:
    secret_store.create_vault("good-password", {"OPENAI_API_KEY": "sk-test"})
    secret_store.lock_vault()
    with pytest.raises(secret_store.VaultError):
        secret_store.unlock_vault("bad-password")
