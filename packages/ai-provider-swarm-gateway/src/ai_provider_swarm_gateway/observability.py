"""Small JSON-line observability helpers for local CLI/MCP workflows."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from typing import Any

_SENSITIVE_PARTS = ("prompt", "secret", "token", "api_key", "key")
_COUNTERS: Counter[str] = Counter()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): "[redacted]" if _is_sensitive_key(str(k)) else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_PARTS)


def log_event(event: str, *, level: str = "info", **fields: Any) -> None:
    """Emit one structured JSON line to stderr, redacting sensitive fields."""
    payload = {
        "ts": round(time.time(), 3),
        "level": level,
        "event": event,
        **{
            key: "[redacted]" if _is_sensitive_key(key) else _redact(value)
            for key, value in fields.items()
        },
    }
    print(json.dumps(payload, sort_keys=True, default=str), file=sys.stderr)


def increment_counter(name: str, value: int = 1) -> None:
    _COUNTERS[name] += value


def counters_snapshot() -> dict[str, int]:
    return dict(_COUNTERS)


__all__ = ["counters_snapshot", "increment_counter", "log_event"]
