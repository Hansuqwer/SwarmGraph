"""Time helpers (F-06B, W6 consolidation).

Wall-clock vs monotonic separation:
  - now_ts()       → wall-clock UNIX timestamp; safe for human display + sortable timestamps
                     across processes, BUT subject to NTP jumps and DST.
  - monotonic_ts() → monotonic clock; safe for duration math (e.g., AgentState.duration_seconds)
                     but NOT comparable across processes.
"""
from __future__ import annotations

import time


def now_ts() -> float:
    """Current UNIX timestamp (wall-clock). Use for created_at / updated_at."""
    return time.time()


def monotonic_ts() -> float:
    """Monotonic timestamp. Use for duration math (started/completed delta)."""
    return time.monotonic()
