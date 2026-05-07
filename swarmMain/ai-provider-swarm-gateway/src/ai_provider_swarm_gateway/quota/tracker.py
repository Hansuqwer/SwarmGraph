"""
AGENT 23 — Usage Update Node Specialist
Quota tracker — local JSON-backed usage tracking. Conservative, audit-friendly.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models.quota import QuotaUsage


_DEFAULT_STORAGE = Path.home() / ".ai_provider_gateway" / "usage.json"


class QuotaTracker:
    """
    Local quota tracker stored as JSON.
    Conservative: treats unknown limits as not free.
    Append-only increments (no hidden counter reset).
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or _DEFAULT_STORAGE
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                self._data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self._data, indent=2, default=str),
            encoding="utf-8",
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def get_usage(self, provider_id: str, window: str = "daily") -> QuotaUsage:
        key = f"{provider_id}:{window}"
        raw = self._data.get(key, {})
        self._maybe_reset(provider_id, window, raw)
        raw = self._data.get(key, {})
        return QuotaUsage(
            provider_id=provider_id,
            window=window,  # type: ignore[arg-type]
            used_requests=raw.get("used_requests", 0),
            used_tokens=raw.get("used_tokens", 0),
            reset_at=datetime.fromisoformat(raw["reset_at"]) if raw.get("reset_at") else None,
        )

    def increment(
        self,
        provider_id: str,
        requests: int = 1,
        tokens: int = 0,
        window: str = "daily",
    ) -> QuotaUsage:
        """Increment usage counters. Always non-negative. Saved to disk."""
        if requests < 0 or tokens < 0:
            raise ValueError("Cannot decrement quota usage")
        key = f"{provider_id}:{window}"
        if key not in self._data:
            self._data[key] = {"used_requests": 0, "used_tokens": 0, "reset_at": None}
        self._data[key]["used_requests"] = self._data[key].get("used_requests", 0) + requests
        self._data[key]["used_tokens"]   = self._data[key].get("used_tokens", 0)   + tokens
        self._save()
        return self.get_usage(provider_id, window)

    def is_exhausted(
        self,
        provider_id: str,
        max_requests: int | None,
        window: str = "daily",
    ) -> bool:
        """
        Returns True if known max_requests is exceeded.
        If max_requests is None (unknown limit) → return False by default
        (caller should apply conservative policy separately).
        """
        if max_requests is None:
            return False  # unknown — caller decides via policy
        usage = self.get_usage(provider_id, window)
        return usage.used_requests >= max_requests

    def set_reset_time(self, provider_id: str, reset_at: datetime, window: str = "daily") -> None:
        key = f"{provider_id}:{window}"
        if key not in self._data:
            self._data[key] = {"used_requests": 0, "used_tokens": 0}
        self._data[key]["reset_at"] = reset_at.isoformat()
        self._save()

    def all_usage(self) -> dict[str, QuotaUsage]:
        result: dict[str, QuotaUsage] = {}
        for key in self._data:
            parts = key.split(":", 1)
            if len(parts) == 2:
                provider_id, window = parts
                result[key] = self.get_usage(provider_id, window)
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    def _maybe_reset(self, provider_id: str, window: str, raw: dict[str, Any]) -> None:
        """Reset counter if reset_at has passed."""
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
                self._data[key] = {"used_requests": 0, "used_tokens": 0, "reset_at": None}
                self._save()
        except (ValueError, TypeError):
            pass
