"""QuotaTracker — patched (v7.1).

History:
  v3–v6 lineage preserved.
  v7: multi-tenant isolation (tenant_id, per-tenant storage path).
  v7.1 — F-29-CORR1: `reset_usage()` must NOT go through `_save_locked()`'s
         merge-with-disk path. The merge takes max(in_memory, on_disk),
         so reset to {used_requests: 0} silently became max(0, 10) = 10.
         Fix: introduce `_authoritative_save_locked()` that writes
         in-memory state verbatim (no merge), and have `reset_usage()` call it.
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
    """Local quota tracker."""

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
        _validate_tenant_id(tenant_id)
        return _DEFAULT_BASE / _TENANTS_SUBDIR / tenant_id / "usage.json"

    @classmethod
    def for_tenant(cls, tenant_id: str) -> "QuotaTracker":
        return cls(tenant_id=tenant_id)

    @classmethod
    def list_tenants(cls) -> list[str]:
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
        """Increment-safe save: merges with on-disk state via max() per counter.

        This is the right semantics for `increment()` because two processes
        racing increments must each see the other's progress (max preserves
        the higher of the two).

        It is the WRONG semantics for `reset_usage()` because reset to 0
        gets swallowed by max(0, on_disk_value) = on_disk_value. Reset
        callers must use `_authoritative_save_locked()` instead.
        """
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
        """F-29-CORR1: write in-memory state verbatim, NO merge.

        Used by reset_usage() — caller's intent is "make this the truth"
        not "advance counters to at least this value". Concurrent writers
        racing against an authoritative reset will see the reset on their
        next read; their own increments after the reset use the normal
        merge path.
        """
        assert self._data is not None
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a+") as lock_fh:
            with _file_lock(lock_fh):
                # NO merge with on-disk — in-memory wins absolutely
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
        self._save_locked()  # merge-safe path for increments
        return self.get_usage(provider_id, window)

    def reset_usage(
        self,
        provider_id: str,
        window: str = "daily",
    ) -> QuotaUsage:
        """F-29-CORR1: reset to zero authoritatively.

        Bypasses the merge-with-disk path so that on-disk counters > 0 are
        not silently preserved via max(in_memory, on_disk).
        """
        self._ensure_loaded()
        assert self._data is not None
        key = f"{provider_id}:{window}"
        self._data[key] = {"used_requests": 0, "used_tokens": 0, "reset_at": None}
        self._authoritative_save_locked()
        # Reload from disk after authoritative write (ensures get_usage sees
        # exactly what's persisted, not any in-memory leftover from before)
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
                # Time-based auto-reset is also authoritative
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
