"""Encrypted account vault for provider keys and session tokens."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_BASE = Path.home() / ".ai_provider_gateway"
DEFAULT_VAULT_PATH = DEFAULT_BASE / "secrets.json.enc"
DEFAULT_KEY_PATH = DEFAULT_BASE / "vault.key"
VAULT_KEY_ENV = "AI_PROVIDER_GATEWAY_VAULT_KEY"


class VaultError(RuntimeError):
    """Raised when vault encryption/decryption cannot proceed safely."""


def _load_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:  # pragma: no cover - optional extra
        raise VaultError("vault support requires the vault extra") from exc
    return Fernet, InvalidToken


def create_vault_key(path: Path | str = DEFAULT_KEY_PATH) -> str:
    """Create a new Fernet key file with 0600 permissions."""
    Fernet, _ = _load_fernet()
    key_path = Path(path)
    if key_path.exists():
        raise VaultError(f"vault key already exists: {key_path}")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key().decode("ascii")
    key_path.write_text(key, encoding="utf-8")
    os.chmod(key_path, 0o600)
    return key


def vault_key_available(key_path: Path | str | None = DEFAULT_KEY_PATH) -> bool:
    """Return whether a vault key is available without exposing its value."""
    if os.environ.get(VAULT_KEY_ENV):
        return True
    return key_path is not None and Path(key_path).exists()


def verify_vault_file(
    path: Path | str,
    *,
    key_path: Path | str | None = DEFAULT_KEY_PATH,
) -> None:
    """Force Fernet decrypt/JSON parse of an encrypted vault file."""
    SecretStore(path, key_path=key_path).to_summary()


class SecretStore:
    """Fail-closed encrypted account store.

    Key source is explicit: ``key``, ``AI_PROVIDER_GATEWAY_VAULT_KEY``, or a
    key file. No hardware-derived keys and no plaintext fallback.
    """

    def __init__(
        self,
        path: Path | str = DEFAULT_VAULT_PATH,
        *,
        key: str | None = None,
        key_path: Path | str | None = DEFAULT_KEY_PATH,
    ) -> None:
        Fernet, InvalidToken = _load_fernet()
        self._invalid_token = InvalidToken
        self.path = Path(path)
        self.key_path = Path(key_path) if key_path is not None else None
        resolved_key = self._resolve_key(key)
        self._fernet = Fernet(resolved_key.encode("ascii"))
        self._data: dict[str, list[dict[str, str]]] = {}
        self._load()

    def _resolve_key(self, explicit: str | None) -> str:
        if explicit:
            return explicit.strip()
        env_key = os.environ.get(VAULT_KEY_ENV)
        if env_key:
            return env_key.strip()
        if self.key_path is not None and self.key_path.exists():
            return self.key_path.read_text(encoding="utf-8").strip()
        raise VaultError(f"vault key missing; set {VAULT_KEY_ENV} or create {self.key_path}")

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        raw = self.path.read_bytes()
        try:
            decoded = self._fernet.decrypt(raw).decode("utf-8")
            data = json.loads(decoded)
        except self._invalid_token as exc:
            raise VaultError("vault decryption failed") from exc
        except Exception as exc:
            raise VaultError("vault file is corrupt") from exc
        if not isinstance(data, dict):
            raise VaultError("vault root must be an object")
        self._data = {
            str(provider): [dict(item) for item in items if isinstance(item, dict)]
            for provider, items in data.items()
            if isinstance(items, list)
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, sort_keys=True).encode("utf-8")
        tmp_path = self.path.with_name(f".{self.path.name}.tmp")
        tmp_path.write_bytes(self._fernet.encrypt(payload))
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self.path)
        os.chmod(self.path, 0o600)

    def add_key(self, provider_id: str, account_id: str, secret: str) -> None:
        if not provider_id or not account_id or not secret:
            raise ValueError("provider_id, account_id, and secret are required")
        entries = self._data.setdefault(provider_id, [])
        for entry in entries:
            if entry.get("account_id") == account_id:
                entry["secret"] = secret
                self._save()
                return
        entries.append({"account_id": account_id, "secret": secret})
        self._save()

    def get_account_ids(self, provider_id: str) -> list[str]:
        return [entry["account_id"] for entry in self._data.get(provider_id, [])]

    def get_key_for_account(self, provider_id: str, account_id: str) -> str | None:
        for entry in self._data.get(provider_id, []):
            if entry.get("account_id") == account_id:
                return entry.get("secret")
        return None

    def to_summary(self) -> dict[str, Any]:
        return {
            provider: [entry["account_id"] for entry in entries]
            for provider, entries in sorted(self._data.items())
        }


__all__ = [
    "DEFAULT_KEY_PATH",
    "DEFAULT_VAULT_PATH",
    "VAULT_KEY_ENV",
    "SecretStore",
    "VaultError",
    "create_vault_key",
    "vault_key_available",
    "verify_vault_file",
]
