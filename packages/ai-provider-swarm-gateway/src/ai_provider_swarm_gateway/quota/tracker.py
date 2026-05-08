"""QuotaTracker — patched (v7: multi-tenant isolation).

v3–v6 lineage preserved:
  - Atomic writes via swarm_shared.atomic_write_json (F-29A)
  - File-locking via fcntl/msvcrt around read-modify-write (F-29B)
  - Lazy load on first get_usage (F-29-PERF1)
  - Injectable storage path (F-29-LG1)
  - reset_usage() helper (your local fix)

v7 NEW:
  - tenant_id parameter (env var: AI_PROVIDER_GATEWAY_TENANT)
  - Per-tenant storage path: ~/.ai_provider_gateway/tenants/<id>/usage.json
  - Single-tenant default unchanged: ~/.ai_provider_gateway/usage.json
  - tenant_storage_path(tenant_id) classmethod for explicit construction
  - QuotaTracker.for_tenant(tenant_id) factory
"""
from __future__ import annotations

import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from swarm_shared.atomic_write import atomic_write_json

from ..models.quota import QuotaUsage


_DEFAULT_BASE = Path.home() / ".ai_provider_gateway"
_DEFAULT_SINGLE_TENANT = _DEFAULT_BASE / "usage.json"
_TENANTS_SUBDIR = "tenants"
_TENANT_ENV = "AI_PROVIDER_GATEWAY_TENANT"

# Tenant ids must be filesystem-safe and not allow path traversal
_TENANT_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _validate_tenant_id(tenant_id: str) -> str:
    if not _TENANT_ID_RE.match(tenant_id):
        raise ValueError(
            f"tenant_id must match [a-zA-Z0-9_-]{{1,64}}; got {tenant_id!r}"
        )
    return tenant_id


# ── Cross-platform file locking ──────────────────────────────────────────

if sys.platform == "win32":
    import msvcrt

    @contextmanager
    def _file_lock(fh) -> Iterator[None]:
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            yield
        finally:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
else:
    import fcntl

    @contextmanager
    def _file_lock(fh) -> Iterator[None]:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class QuotaTracker:
    """Local quota tracker.

    Default (single-tenant): ~/.ai_provider_gateway/usage.json
    Tenant: ~/.ai_provider_gateway/tenants/<tenant_id>/usage.json
    """

    def __init__(
        self,
        storage_path: Path | None = None,
        *,
        tenant_id: str | None = None,
    ) -> None:
        if storage_path is not None and tenant_id is not None:
            raise ValueError("specify either storage_path OR tenant_id, not both")

        if storage_path is not None:
            self.storage_path = Path(storage_path)
            self.tenant_id: str | None = None
        elif tenant_id is not None:
            self.tenant_id = _validate_tenant_id(tenant_id)
            self.storage_path = self.tenant_storage_path(self.tenant_id)
        else:
            # Auto-detect from env
            env_tenant = os.environ.get(_TENANT_ENV, "").strip()
            if env_tenant:
                self.tenant_id = _validate_tenant_id(env_tenant)
                self.storage_path = self.tenant_storage_path(self.tenant_id)
            else:
                self.tenant_id = None
                self.storage_path = _DEFAULT_SINGLE_TENANT

        self._lock_path = self.storage_path.with_suffix(self.storage_path.suffix + ".lock")
        self._data: dict[str, dict[str, Any]] | None = None

    @classmethod
    def tenant_storage_path(cls, tenant_id: str) -> Path:
        """Return the canonical storage path for a tenant."""
        _validate_tenant_id(tenant_id)
        return _DEFAULT_BASE / _TENANTS_SUBDIR / tenant_id / "usage.json"

    @classmethod
    def for_tenant(cls, tenant_id: str) -> "QuotaTracker":
        """Factory: construct a tenant-isolated tracker."""
        return cls(tenant_id=tenant_id)

    @classmethod
    def list_tenants(cls) -> list[str]:
        """List tenant ids that have a usage.json on disk."""
        tenants_dir = _DEFAULT_BASE / _TENANTS_SUBDIR
        if not tenants_dir.exists():
            return []
        out: list[str] = []
        for child in sorted(tenants_dir.iterdir()):
            if child.is_dir() and (child / "usage.json").exists():
                if _TENANT_ID_RE.match(child.name):
                    out.append(child.name)
        return out

    # ── Persistence ──────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._data is not None:
            return
        if self.storage_path.exists():
            try:
                self._data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _save_locked(self) -> None:
        assert self._data is not None
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a+") as lock_fh:
            with _file_lock(lock_fh):
                if self.storage_path.exists():
                    try:
                        on_disk = json.loads(self.storage_path.read_text(encoding="utf-8"))
                        merged: dict[str, dict[str, Any]] = {}
                        all_keys = set(on_disk) | set(self._data)
                        for k in all_keys:
                            ours = self._data.get(k, {})
                            theirs = on_disk.get(k, {})
                            merged[k] = {
                                "used_requests": max(
                                    ours.get("used_requests", 0),
                                    theirs.get("used_requests", 0),
                                ),
                                "used_tokens": max(
                                    ours.get("used_tokens", 0),
                                    theirs.get("used_tokens", 0),
                                ),
                                "reset_at": ours.get("reset_at") or theirs.get("reset_at"),
                            }
                        self._data = merged
                    except (json.JSONDecodeError, OSError):
                        pass
                atomic_write_json(self.storage_path, self._data, default=str)

    def _authoritative_save_locked(self) -> None:
        """Write in-memory state verbatim, with no merge against disk."""
        assert self._data is not None
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a+") as lock_fh:
            with _file_lock(lock_fh):
                atomic_write_json(self.storage_path, self._data, default=str)

    # ── Public API ───────────────────────────────────────────────────────

    def get_usage(self, provider_id: str, window: str = "daily") -> QuotaUsage:
        self._ensure_loaded()
        assert self._data is not None
        key = f"{provider_id}:{window}"
        raw = self._data.get(key, {})
        self._maybe_reset(provider_id, window, raw)
        raw = self._data.get(key, {})
        return QuotaUsage(
            provider_id=provider_id,
            window=window,  # type: ignore[arg-type]
            used_requests=raw.get("used_requests", 0),
            used_tokens=raw.get("used_tokens", 0),
            reset_at=(
                datetime.fromisoformat(raw["reset_at"])
                if raw.get("reset_at") else None
            ),
        )

    def increment(
        self,
        provider_id: str,
        requests: int = 1,
        tokens: int = 0,
        window: str = "daily",
    ) -> QuotaUsage:
        if requests < 0 or tokens < 0:
            raise ValueError("Cannot decrement quota usage")
        self._ensure_loaded()
        assert self._data is not None
        key = f"{provider_id}:{window}"
        if key not in self._data:
            self._data[key] = {"used_requests": 0, "used_tokens": 0, "reset_at": None}
        self._data[key]["used_requests"] = self._data[key].get("used_requests", 0) + requests
        self._data[key]["used_tokens"] = self._data[key].get("used_tokens", 0) + tokens
        self._save_locked()
        return self.get_usage(provider_id, window)

    def reset_usage(
        self,
        provider_id: str,
        window: str = "daily",
    ) -> QuotaUsage:
        """Reset a counter to zero. (Your local v3-era fix; preserved.)"""
        self._ensure_loaded()
        assert self._data is not None
        key = f"{provider_id}:{window}"
        self._data[key] = {"used_requests": 0, "used_tokens": 0, "reset_at": None}
        self._authoritative_save_locked()
        self._data = None
        self._ensure_loaded()
        return self.get_usage(provider_id, window)

    def is_exhausted(
        self,
        provider_id: str,
        max_requests: int | None,
        window: str = "daily",
    ) -> bool:
        if max_requests is None:
            return False
        usage = self.get_usage(provider_id, window)
        return usage.used_requests >= max_requests

    def set_reset_time(
        self,
        provider_id: str,
        reset_at: datetime,
        window: str = "daily",
    ) -> None:
        self._ensure_loaded()
        assert self._data is not None
        key = f"{provider_id}:{window}"
        if key not in self._data:
            self._data[key] = {"used_requests": 0, "used_tokens": 0}
        self._data[key]["reset_at"] = reset_at.isoformat()
        self._save_locked()

    def all_usage(self) -> dict[str, QuotaUsage]:
        self._ensure_loaded()
        assert self._data is not None
        result: dict[str, QuotaUsage] = {}
        for key in self._data:
            parts = key.split(":", 1)
            if len(parts) == 2:
                provider_id, window = parts
                result[key] = self.get_usage(provider_id, window)
        return result

    # ── Private ──────────────────────────────────────────────────────────

    def _maybe_reset(self, provider_id: str, window: str, raw: dict[str, Any]) -> None:
        reset_at_str = raw.get("reset_at")
        if not reset_at_str:
            return
        try:
            reset_at = datetime.fromisoformat(reset_at_str)
            if reset_at.tzinfo is None:
                reset_at = reset_at.replace(tzinfo=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            if now >= reset_at:
                key = f"{provider_id}:{window}"
                assert self._data is not None
                self._data[key] = {
                    "used_requests": 0,
                    "used_tokens": 0,
                    "reset_at": None,
                }
                self._authoritative_save_locked()
        except (ValueError, TypeError):
            pass


__all__ = ["QuotaTracker"]
