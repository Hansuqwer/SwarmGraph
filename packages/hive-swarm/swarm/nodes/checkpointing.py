"""Checkpointing — patched.

F-W6A: SwarmRedactingCheckpointer now subclasses BaseRedactingCheckpointer
       from swarm-shared (eliminates duplication).
F-20A (CRITICAL): production redaction regex set inherited from swarm_shared.redaction
F-20B: FileCheckpointStore.load_latest sorts by encoded iteration in filename
       (NTP-jump safe) instead of stat().st_mtime
F-20C: extracted into shared package
F-20D: secrets.token_hex(8) for checkpoint IDs (was 4)
F-20-SEC2: dict KEYS also redacted (inherited from swarm_shared.redaction.redact_obj)
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

from swarm_shared.atomic_write import atomic_write_json
from swarm_shared.checkpointing import BaseRedactingCheckpointer
from swarm_shared.redaction import Redactor

from ..models.state import SwarmCheckpoint, SwarmState


# ── In-process store ──────────────────────────────────────────────────────

class InProcessCheckpointStore:
    """In-process checkpointing for development and testing."""

    def __init__(self) -> None:
        self._store: dict[str, SwarmCheckpoint] = {}

    def save(self, state: SwarmState) -> SwarmCheckpoint:
        # F-20D: 16-hex-char random suffix
        cp_id = f"cp-{state.swarm_id}-{state.iteration:06d}-{secrets.token_hex(8)}"
        checkpoint = SwarmCheckpoint.from_state(state, cp_id)
        self._store[cp_id] = checkpoint
        return checkpoint

    def load_latest(self, swarm_id: str) -> SwarmState | None:
        candidates = [
            cp for cp in self._store.values() if cp.swarm_id == swarm_id
        ]
        if not candidates:
            return None
        # F-20B: prefer iteration order over wall-clock
        latest = max(candidates, key=lambda c: (c.iteration, c.created_at))
        return latest.restore()

    def list_checkpoints(self, swarm_id: str) -> list[SwarmCheckpoint]:
        return sorted(
            [cp for cp in self._store.values() if cp.swarm_id == swarm_id],
            key=lambda c: (c.iteration, c.created_at),
        )


# ── File-backed store ────────────────────────────────────────────────────

# F-20B: filename pattern with zero-padded iteration for sortable globbing
_CP_FILENAME_RE = re.compile(r"^cp-(.+)-(\d{6})-([0-9a-f]+)\.json$")


class FileCheckpointStore:
    """File-backed atomic checkpoint store."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, state: SwarmState) -> SwarmCheckpoint:
        cp_id = f"cp-{state.swarm_id}-{state.iteration:06d}-{secrets.token_hex(8)}"
        checkpoint = SwarmCheckpoint.from_state(state, cp_id)
        target = self.directory / f"{cp_id}.json"
        # F-W6: shared atomic_write_json
        atomic_write_json(target, checkpoint.model_dump(mode="json"))
        return checkpoint

    def load_latest(self, swarm_id: str) -> SwarmState | None:
        candidates: list[tuple[int, Path]] = []
        for p in self.directory.glob(f"cp-{swarm_id}-*.json"):
            m = _CP_FILENAME_RE.match(p.name)
            if not m or m.group(1) != swarm_id:
                continue
            iteration = int(m.group(2))
            candidates.append((iteration, p))
        if not candidates:
            return None
        # F-20B: sort by iteration encoded in filename (NTP-jump safe)
        candidates.sort(key=lambda t: t[0], reverse=True)
        latest_file = candidates[0][1]
        data = json.loads(latest_file.read_text(encoding="utf-8"))
        cp = SwarmCheckpoint.model_validate(data)
        return cp.restore()


# ── LangGraph-compatible RedactingCheckpointer ────────────────────────────

class SwarmRedactingCheckpointer(BaseRedactingCheckpointer):
    """Wraps any LangGraph saver. F-20A: inherits production-grade regex set.

    All 8 BaseCheckpointSaver methods are implemented in BaseRedactingCheckpointer.
    The CI guard test is in swarm-shared/tests/test_checkpointing_coverage.py.
    """

    def __init__(self, inner: Any, *, detect_high_entropy: bool = False) -> None:
        super().__init__(inner, redactor=Redactor(detect_high_entropy=detect_high_entropy))


__all__ = [
    "InProcessCheckpointStore",
    "FileCheckpointStore",
    "SwarmRedactingCheckpointer",
]
