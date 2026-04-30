"""Encrypted local API-key vault and provider client helpers."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import threading
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VAULT_FILENAME = "secrets.vault"
VAULT_VERSION = 1
KDF_NAME = "pbkdf2-sha256"
KDF_ITERATIONS = 600_000
KEY_BYTES = 32

SecretName = Literal["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "REPLICATE_API_TOKEN"]
PROVIDERS: dict[str, SecretName] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "replicate": "REPLICATE_API_TOKEN",
}

_runtime_lock = threading.Lock()
_runtime_secrets: dict[str, str] = {}
_runtime_key: bytes | None = None
_runtime_salt: bytes | None = None
_runtime_iterations: int = KDF_ITERATIONS
_runtime_previous_env: dict[str, str | None] = {}


class VaultLocked(RuntimeError):
    pass


class VaultError(RuntimeError):
    pass


def config_root() -> Path:
    override = os.environ.get("BDGEN_CONFIG_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "BdGEN"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "BdGEN"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "bdgen"


def vault_path() -> Path:
    return config_root() / VAULT_FILENAME


def has_vault() -> bool:
    return vault_path().exists()


def is_unlocked() -> bool:
    with _runtime_lock:
        return bool(_runtime_secrets)


def lock_vault() -> None:
    global _runtime_key, _runtime_salt, _runtime_iterations, _runtime_previous_env
    with _runtime_lock:
        previous = dict(_runtime_previous_env)
        _runtime_secrets.clear()
        _runtime_key = None
        _runtime_salt = None
        _runtime_iterations = KDF_ITERATIONS
        _runtime_previous_env = {}
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def get_secret(name: SecretName) -> str | None:
    with _runtime_lock:
        value = _runtime_secrets.get(name)
    if value:
        return value
    return os.environ.get(name)


def require_secret(name: SecretName) -> str:
    value = get_secret(name)
    if not value:
        raise RuntimeError(
            f"{name} non defini. Configurez la cle API dans le coffre BdGEN "
            "ou dans le fichier .env en mode developpement."
        )
    return value


def provider_status() -> dict[str, dict]:
    with _runtime_lock:
        runtime = dict(_runtime_secrets)
    out: dict[str, dict] = {}
    for provider, secret_name in PROVIDERS.items():
        source = None
        if runtime.get(secret_name):
            source = "vault"
        elif os.environ.get(secret_name):
            source = "env"
        out[provider] = {
            "secret_name": secret_name,
            "configured": source is not None,
            "source": source,
        }
    return out


def status() -> dict:
    return {
        "vault_exists": has_vault(),
        "unlocked": is_unlocked(),
        "vault_path": str(vault_path()),
        "providers": provider_status(),
    }


def create_vault(password: str, secrets: dict[str, str], overwrite: bool = False) -> dict:
    path = vault_path()
    if path.exists() and not overwrite:
        raise VaultError("Un coffre existe deja.")
    clean = _clean_secrets(secrets)
    if not clean:
        raise VaultError("Ajoutez au moins une cle API avant de creer le coffre.")
    payload, key, salt = _encrypt(password, clean)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    _set_runtime(clean, key=key, salt=salt, iterations=KDF_ITERATIONS)
    return status()


def unlock_vault(password: str) -> dict:
    path = vault_path()
    if not path.exists():
        raise VaultError("Aucun coffre BdGEN n'existe encore.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        secrets, key, salt, iterations = _decrypt(password, payload)
    except Exception as exc:
        raise VaultError("Mot de passe incorrect ou coffre illisible.") from exc
    _set_runtime(secrets, key=key, salt=salt, iterations=iterations)
    return status()


def update_secret(name: SecretName, value: str | None) -> dict:
    with _runtime_lock:
        if not _runtime_secrets and has_vault():
            raise VaultLocked("Le coffre est verrouille.")
        if value and value.strip():
            _runtime_secrets[name] = value.strip()
        else:
            _runtime_secrets.pop(name, None)
            if name in os.environ and not has_vault():
                os.environ.pop(name, None)
        runtime = dict(_runtime_secrets)
        key = _runtime_key
        salt = _runtime_salt
        iterations = _runtime_iterations
    if has_vault() and key and salt:
        _write_payload(_encrypt_with_key(runtime, key, salt, iterations))
    _apply_runtime_env(runtime)
    return status()


def save_unlocked(password: str) -> dict:
    with _runtime_lock:
        if not _runtime_secrets:
            raise VaultLocked("Le coffre est verrouille.")
        clean = dict(_runtime_secrets)
    return create_vault(password, clean, overwrite=True)


def openai_client():
    from openai import OpenAI

    return OpenAI(api_key=require_secret("OPENAI_API_KEY"))


def anthropic_client():
    import anthropic

    return anthropic.Anthropic(api_key=require_secret("ANTHROPIC_API_KEY"))


def ensure_replicate_env() -> str:
    token = require_secret("REPLICATE_API_TOKEN")
    os.environ["REPLICATE_API_TOKEN"] = token
    return token


def _clean_secrets(secrets: dict[str, str]) -> dict[str, str]:
    allowed = set(PROVIDERS.values())
    return {
        k: v.strip()
        for k, v in secrets.items()
        if k in allowed and isinstance(v, str) and v.strip()
    }


def _set_runtime(
    secrets: dict[str, str],
    key: bytes | None = None,
    salt: bytes | None = None,
    iterations: int = KDF_ITERATIONS,
) -> None:
    global _runtime_key, _runtime_salt, _runtime_iterations
    clean = _clean_secrets(secrets)
    with _runtime_lock:
        _runtime_secrets.clear()
        _runtime_secrets.update(clean)
        _runtime_key = key
        _runtime_salt = salt
        _runtime_iterations = iterations
    _apply_runtime_env(clean)


def _apply_runtime_env(secrets: dict[str, str]) -> None:
    global _runtime_previous_env
    allowed = set(PROVIDERS.values())
    with _runtime_lock:
        for key in secrets:
            if key not in _runtime_previous_env:
                _runtime_previous_env[key] = os.environ.get(key)
        for key in allowed:
            if key in secrets:
                os.environ[key] = secrets[key]
            elif key in _runtime_previous_env:
                previous = _runtime_previous_env.pop(key)
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous


def _encrypt(password: str, secrets: dict[str, str]) -> tuple[dict, bytes, bytes]:
    if not password:
        raise VaultError("Le mot de passe maitre est obligatoire.")
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    return _encrypt_with_key(secrets, key, salt, KDF_ITERATIONS), key, salt


def _encrypt_with_key(
    secrets: dict[str, str],
    key: bytes,
    salt: bytes,
    iterations: int = KDF_ITERATIONS,
) -> dict:
    nonce = os.urandom(12)
    data = json.dumps(secrets, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return {
        "version": VAULT_VERSION,
        "kdf": KDF_NAME,
        "iterations": iterations,
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
    }


def _decrypt(password: str, payload: dict) -> tuple[dict[str, str], bytes, bytes, int]:
    if payload.get("version") != VAULT_VERSION:
        raise VaultError("Version de coffre non supportee.")
    if payload.get("kdf") != KDF_NAME:
        raise VaultError("KDF de coffre non supporte.")
    salt = _unb64(payload["salt"])
    nonce = _unb64(payload["nonce"])
    ciphertext = _unb64(payload["ciphertext"])
    iterations = int(payload.get("iterations") or KDF_ITERATIONS)
    key = _derive_key(password, salt, iterations)
    data = AESGCM(key).decrypt(nonce, ciphertext, None)
    decoded = json.loads(data.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise VaultError("Contenu de coffre invalide.")
    return _clean_secrets(decoded), key, salt, iterations


def _write_payload(payload: dict) -> None:
    path = vault_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _derive_key(password: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=KEY_BYTES,
    )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))
