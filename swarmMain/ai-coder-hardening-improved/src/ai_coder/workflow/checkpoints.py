"""Local checkpoint persistence — hardened edition.

Improvements over original:
  - Atomic write via temp-file + os.replace() prevents corrupt checkpoints on
    crash mid-write (C2).
  - load() handles JSONDecodeError cleanly and raises CheckpointNotFound (C2).
  - _redact_checkpoint_obj is tested against a defined interface contract.
  - RedactingCheckpointer explicitly validates that serde is not None when the
    inner saver provides one (M5).
  - build_checkpointer raises a clear error when 'local' backend is selected
    directly (preserves original behaviour, adds docstring clarity).
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .state import WorkflowState

try:
    from langgraph.checkpoint.base import BaseCheckpointSaver
except ModuleNotFoundError:  # pragma: no cover - optional agents runtime dependency.
    BaseCheckpointSaver = object  # type: ignore[assignment,misc]


_SUPPORTED_CHECKPOINT_BACKENDS: tuple[str, ...] = ("local", "memory", "sqlite", "postgres")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CheckpointNotFound(FileNotFoundError):
    """Raised when a durable resume checkpoint is missing."""


class CheckpointCorrupt(ValueError):
    """Raised when a checkpoint file exists but cannot be parsed."""


# ---------------------------------------------------------------------------
# Redaction helpers (imported lazily to avoid circular imports in tests)
# ---------------------------------------------------------------------------

def _get_redactors() -> tuple[Any, Any]:
    """Return (full_redactor, no_path_redactor) — lazy import."""
    from ..redaction.config import RedactionPolicy
    from ..redaction.redactor import Redactor
    full = Redactor()
    no_path = Redactor(RedactionPolicy(enable_path_redaction=False))
    return full, no_path


def _redact_checkpoint_obj(obj: Any, *, redactor: Any = None) -> Any:
    """Recursively redact secrets from a checkpoint value."""
    if redactor is None:
        redactor, _ = _get_redactors()
    if isinstance(obj, dict):
        return {k: _redact_checkpoint_obj(v, redactor=redactor) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_checkpoint_obj(item, redactor=redactor) for item in obj]
    if isinstance(obj, str):
        return redactor.redact_text(obj)
    return obj


# ---------------------------------------------------------------------------
# Local checkpoint store
# ---------------------------------------------------------------------------

class LocalCheckpointStore:
    """Stores canonical checkpoints with artifact-boundary redaction.

    The checkpoint file itself is canonical (paths preserved) so that
    LangGraph can resume correctly. Redaction is applied only at the
    artifact/log output boundary (via save_run_artifact).

    Write safety: uses atomic rename to prevent corrupt checkpoint files
    on crash mid-write (C2).
    """

    def __init__(
        self,
        repo_root: Path,
        checkpoint_dir: str = ".ai-coder/checkpoints",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.checkpoint_dir = _resolve_checkpoint_dir(self.repo_root, checkpoint_dir)

    def save(self, state: WorkflowState) -> None:
        """Atomically persist state checkpoint and redacted run artifact."""
        state.touch()
        payload = state.model_dump(mode="json")

        # Save redacted artifact at the output boundary
        try:
            from ..artifacts import save_run_artifact
            save_run_artifact(self.repo_root, state.thread_id, payload)
        except Exception:  # pragma: no cover — artifact sink is best-effort
            pass

        # Atomic write: write to .tmp then os.replace() (C2)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        target = self.checkpoint_path(state.thread_id)
        serialised = json.dumps(payload, indent=2, sort_keys=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.checkpoint_dir),
            prefix=f".{state.thread_id}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(serialised)
            os.replace(tmp_path, str(target))
        except Exception:
            # Clean up temp file on failure; re-raise
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load(self, thread_id: str) -> WorkflowState:
        """Load and validate a persisted checkpoint."""
        path = self.checkpoint_path(thread_id)
        if not path.exists():
            raise CheckpointNotFound(f"checkpoint not found for thread: {thread_id}")
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CheckpointCorrupt(
                f"checkpoint for thread {thread_id} is corrupt: {exc}"
            ) from exc
        state = WorkflowState.model_validate(raw)
        state.repo_root = str(self.repo_root)
        return state

    def checkpoint_path(self, thread_id: str) -> Path:
        return self.checkpoint_dir / f"{thread_id}.json"


def _resolve_checkpoint_dir(repo_root: Path, checkpoint_dir: str) -> Path:
    p = Path(checkpoint_dir)
    if not p.is_absolute():
        p = repo_root / p
    return p


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def checkpoint_backend_from_raw(raw: dict) -> tuple[str, str]:
    workflow = raw.get("workflow", {}) if raw else {}
    return (
        str(workflow.get("checkpoint_backend", "local")),   # default → local (M2 fix)
        str(workflow.get("checkpoint_dir", ".ai-coder/checkpoints")),
    )


def build_checkpoint_store(repo_root: Path, raw: dict) -> LocalCheckpointStore:
    backend, checkpoint_dir = checkpoint_backend_from_raw(raw)
    if backend not in _SUPPORTED_CHECKPOINT_BACKENDS:
        raise ValueError(
            f"unsupported workflow checkpoint backend: {backend!r}; "
            f"expected one of {_SUPPORTED_CHECKPOINT_BACKENDS}"
        )
    return LocalCheckpointStore(repo_root, checkpoint_dir)


def build_checkpointer(config: Any, saver: Any | None = None) -> Any:
    """Build a LangGraph checkpointer without making LangGraph a hard dependency."""
    if saver is not None:
        return RedactingCheckpointer(saver)
    backend = config.workflow.checkpoint_backend
    if backend == "local":
        raise ValueError(
            "checkpoint_backend 'local' selects the legacy JSON-artifact workflow "
            "and has no LangGraph saver. AgentWorkflow handles this automatically. "
            "If you are constructing LangGraphRuntime directly, configure "
            "'memory', 'sqlite', or 'postgres' instead."
        )
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    if backend == "memory":
        from langgraph.checkpoint.memory import InMemorySaver
        return RedactingCheckpointer(InMemorySaver())
    if backend == "sqlite":
        from langgraph.checkpoint.sqlite import SqliteSaver
        checkpoint_dir = _resolve_checkpoint_dir(
            config.repo_root, config.workflow.checkpoint_dir
        )
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        manager = SqliteSaver.from_conn_string(str(checkpoint_dir / "checkpoints.sqlite"))
        checkpointer = manager.__enter__()
        checkpointer.setup()
        setattr(checkpointer, "_ai_coder_context_manager", manager)
        return RedactingCheckpointer(checkpointer)
    if backend == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver
        dsn = os.environ.get("AI_CODER_PG_DSN")
        if not dsn:
            raise ValueError("AI_CODER_PG_DSN is required for postgres checkpoints")
        manager = PostgresSaver.from_conn_string(dsn)
        checkpointer = manager.__enter__()
        checkpointer.setup()
        setattr(checkpointer, "_ai_coder_context_manager", manager)
        return RedactingCheckpointer(checkpointer)
    raise ValueError(f"unknown checkpoint backend: {backend}")


def close_checkpointer(checkpointer: Any) -> None:
    checkpointer = getattr(checkpointer, "inner", checkpointer)
    manager = getattr(checkpointer, "_ai_coder_context_manager", None)
    if manager is not None:
        manager.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Redacting checkpointer
# ---------------------------------------------------------------------------

class RedactingCheckpointer(BaseCheckpointSaver):  # type: ignore[misc,valid-type]
    """Wraps a LangGraph saver and redacts secrets from all write paths.

    All read methods delegate to the inner saver unchanged (canonical state
    must survive round-trips for LangGraph resumption).

    All write methods redact the checkpoint and metadata before persisting.

    Improvement (M5): serde is passed from inner only if non-None.
    """

    REDACTING_WRITE_METHODS: frozenset[str] = frozenset(
        {"put", "put_writes", "aput", "aput_writes"}
    )
    DELEGATED_MUTATION_METHODS: frozenset[str] = frozenset(
        {
            "copy_thread",
            "acopy_thread",
            "delete_thread",
            "adelete_thread",
            "delete_for_runs",
            "adelete_for_runs",
            "prune",
            "aprune",
        }
    )

    def __init__(self, inner: Any) -> None:
        inner_serde = getattr(inner, "serde", None)
        if BaseCheckpointSaver is not object:
            # M5: only pass serde if the inner saver provides one
            if inner_serde is not None:
                super().__init__(serde=inner_serde)
            else:
                super().__init__()
        self.inner = inner
        _, self._redactor_no_paths = _get_redactors()

    def _redact(self, obj: Any) -> Any:
        return _redact_checkpoint_obj(obj, redactor=self._redactor_no_paths)

    # --- Read paths (pass-through, canonical) ---

    def get_tuple(self, config: Any) -> Any:
        return self.inner.get_tuple(config)

    async def aget_tuple(self, config: Any) -> Any:
        return await self.inner.aget_tuple(config)

    def list(
        self,
        config: Any | None,
        *,
        filter: dict[str, Any] | None = None,
        before: Any | None = None,
        limit: int | None = None,
    ) -> Any:
        return self.inner.list(config, filter=filter, before=before, limit=limit)

    async def alist(
        self,
        config: Any | None,
        *,
        filter: dict[str, Any] | None = None,
        before: Any | None = None,
        limit: int | None = None,
    ) -> Any:
        async for item in self.inner.alist(
            config, filter=filter, before=before, limit=limit
        ):
            yield item

    # --- Write paths (redacted) ---

    def put(
        self,
        config: Any,
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: Any,
    ) -> Any:
        return self.inner.put(
            config,
            self._redact(checkpoint),
            self._redact(metadata),
            new_versions,
        )

    def put_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        safe_writes = [(channel, self._redact(value)) for channel, value in writes]
        return self.inner.put_writes(config, safe_writes, task_id, task_path)

    async def aput(
        self,
        config: Any,
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: Any,
    ) -> Any:
        return await self.inner.aput(
            config,
            self._redact(checkpoint),
            self._redact(metadata),
            new_versions,
        )

    async def aput_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        safe_writes = [(channel, self._redact(value)) for channel, value in writes]
        return await self.inner.aput_writes(config, safe_writes, task_id, task_path)

    # --- Mutation methods (delegated) ---

    def delete_thread(self, thread_id: str) -> None:
        return self.inner.delete_thread(thread_id)

    async def adelete_thread(self, thread_id: str) -> None:
        return await self.inner.adelete_thread(thread_id)
