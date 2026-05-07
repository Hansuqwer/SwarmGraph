"""
AGENT 20 — Checkpointing Specialist
BaseCheckpointSaver compatibility, atomic writes, restart-safe state dumps.
Ruflo: 'Run frequent checkpoints via post-task hooks'
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any, Sequence

from ..models.state import SwarmCheckpoint, SwarmState

try:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    _HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover
    BaseCheckpointSaver = object  # type: ignore[assignment,misc]
    _HAS_LANGGRAPH = False


# ---------------------------------------------------------------------------
# Simple in-process checkpoint store (no external dependency)
# ---------------------------------------------------------------------------

class InProcessCheckpointStore:
    """
    In-process checkpointing for development and testing.
    Production: swap for SqliteCheckpointStore or PostgresCheckpointStore.
    """

    def __init__(self) -> None:
        self._store: dict[str, SwarmCheckpoint] = {}

    def save(self, state: SwarmState) -> SwarmCheckpoint:
        cp_id = f"cp-{state.swarm_id}-{state.iteration}-{secrets.token_hex(4)}"
        checkpoint = SwarmCheckpoint.from_state(state, cp_id)
        self._store[cp_id] = checkpoint
        return checkpoint

    def load_latest(self, swarm_id: str) -> SwarmState | None:
        candidates = [
            cp for cp in self._store.values() if cp.swarm_id == swarm_id
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda c: c.created_at)
        return latest.restore()

    def list_checkpoints(self, swarm_id: str) -> list[SwarmCheckpoint]:
        return sorted(
            [cp for cp in self._store.values() if cp.swarm_id == swarm_id],
            key=lambda c: c.created_at,
        )


# ---------------------------------------------------------------------------
# File-based checkpoint store (atomic writes — crash-safe)
# ---------------------------------------------------------------------------

class FileCheckpointStore:
    """
    File-backed checkpoint store.
    Uses temp-file + os.replace() for atomic writes (crash-safe).
    Ruflo: 'post-task hooks → frequent checkpoint saves'
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, state: SwarmState) -> SwarmCheckpoint:
        cp_id = f"cp-{state.swarm_id}-{state.iteration}-{secrets.token_hex(4)}"
        checkpoint = SwarmCheckpoint.from_state(state, cp_id)
        target = self.directory / f"{cp_id}.json"
        serialized = json.dumps(checkpoint.model_dump(mode="json"), indent=2, sort_keys=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.directory), prefix=f".{cp_id}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(serialized)
            os.replace(tmp_path, str(target))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return checkpoint

    def load_latest(self, swarm_id: str) -> SwarmState | None:
        candidates = list(self.directory.glob(f"cp-{swarm_id}-*.json"))
        if not candidates:
            return None
        latest_file = max(candidates, key=lambda p: p.stat().st_mtime)
        data = json.loads(latest_file.read_text())
        cp = SwarmCheckpoint.model_validate(data)
        return cp.restore()


# ---------------------------------------------------------------------------
# LangGraph-compatible RedactingCheckpointer
# ---------------------------------------------------------------------------

class SwarmRedactingCheckpointer(BaseCheckpointSaver):  # type: ignore[misc,valid-type]
    """
    Wraps any inner LangGraph saver.
    Redacts secrets from checkpoint writes (mirrors ai-coder-hardening pattern).
    """

    def __init__(self, inner: Any) -> None:
        inner_serde = getattr(inner, "serde", None)
        if _HAS_LANGGRAPH and inner_serde is not None:
            super().__init__(serde=inner_serde)
        elif _HAS_LANGGRAPH:
            super().__init__()
        self.inner = inner

    def _redact(self, obj: Any) -> Any:
        """Basic secret redaction — extend with real Redactor in production."""
        if isinstance(obj, dict):
            return {k: self._redact(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._redact(item) for item in obj]
        if isinstance(obj, str) and len(obj) > 40 and obj.startswith("sk-"):
            return "[REDACTED]"
        return obj

    def get_tuple(self, config: Any) -> Any:
        return self.inner.get_tuple(config)

    async def aget_tuple(self, config: Any) -> Any:
        return await self.inner.aget_tuple(config)

    def list(self, config: Any | None, *, filter: Any = None, before: Any = None, limit: Any = None) -> Any:
        return self.inner.list(config, filter=filter, before=before, limit=limit)

    async def alist(self, config: Any | None, *, filter: Any = None, before: Any = None, limit: Any = None) -> Any:
        async for item in self.inner.alist(config, filter=filter, before=before, limit=limit):
            yield item

    def put(self, config: Any, checkpoint: dict[str, Any], metadata: dict[str, Any], new_versions: Any) -> Any:
        return self.inner.put(config, self._redact(checkpoint), self._redact(metadata), new_versions)

    def put_writes(self, config: Any, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        safe = [(ch, self._redact(v)) for ch, v in writes]
        return self.inner.put_writes(config, safe, task_id, task_path)

    async def aput(self, config: Any, checkpoint: dict[str, Any], metadata: dict[str, Any], new_versions: Any) -> Any:
        return await self.inner.aput(config, self._redact(checkpoint), self._redact(metadata), new_versions)

    async def aput_writes(self, config: Any, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        safe = [(ch, self._redact(v)) for ch, v in writes]
        return await self.inner.aput_writes(config, safe, task_id, task_path)
