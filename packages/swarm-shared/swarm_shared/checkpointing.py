"""BaseRedactingCheckpointer (F-W6A; replaces 2 duplications).

Wraps any LangGraph BaseCheckpointSaver and applies redaction to all
write paths (put, put_writes, aput, aput_writes). Read paths
(get_tuple, list, aget_tuple, alist) are passed through unchanged
because checkpoints we wrote are already redacted, and we must preserve
them verbatim for resume to work.

Coverage guard: ALL 8 abstract methods are explicitly implemented.
There is NO __getattr__ proxy (would silently bypass redaction if
LangGraph 0.4 added a new write method).

Test recipe (also shipped in tests/test_checkpointing_coverage.py):

    def test_covers_all_abstract_methods():
        from langgraph.checkpoint.base import BaseCheckpointSaver
        abstract = set(BaseCheckpointSaver.__abstractmethods__)
        implemented = {m for m in abstract if m in BaseRedactingCheckpointer.__dict__}
        missing = abstract - implemented
        assert not missing, f"BaseRedactingCheckpointer missing: {missing}"
"""
from __future__ import annotations

from typing import Any, Sequence

from .redaction import Redactor

try:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    _HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover - optional dependency
    BaseCheckpointSaver = object  # type: ignore[assignment,misc]
    _HAS_LANGGRAPH = False


class BaseRedactingCheckpointer(BaseCheckpointSaver):  # type: ignore[misc,valid-type]
    """Composition wrapper: redact-on-write, pass-through-on-read."""

    def __init__(self, inner: Any, redactor: Redactor | None = None) -> None:
        if _HAS_LANGGRAPH:
            inner_serde = getattr(inner, "serde", None)
            if inner_serde is not None:
                super().__init__(serde=inner_serde)
            else:
                super().__init__()
        self.inner = inner
        self.redactor = redactor or Redactor()
        self._redaction_count = 0

    # ── Sync read paths (pass-through) ─────────────────────────────────────
    def get_tuple(self, config: Any) -> Any:
        return self.inner.get_tuple(config)

    def list(  # noqa: A003 - matches BaseCheckpointSaver signature
        self,
        config: Any | None,
        *,
        filter: Any = None,
        before: Any = None,
        limit: Any = None,
    ) -> Any:
        return self.inner.list(config, filter=filter, before=before, limit=limit)

    # ── Sync write paths (redact) ──────────────────────────────────────────
    def put(
        self,
        config: Any,
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: Any,
    ) -> Any:
        self._redaction_count += 1
        return self.inner.put(
            config,
            self.redactor.redact(checkpoint),
            self.redactor.redact(metadata),
            new_versions,
        )

    def put_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._redaction_count += 1
        safe = [(ch, self.redactor.redact(v)) for ch, v in writes]
        return self.inner.put_writes(config, safe, task_id, task_path)

    # ── Async read paths (pass-through) ────────────────────────────────────
    async def aget_tuple(self, config: Any) -> Any:
        return await self.inner.aget_tuple(config)

    async def alist(
        self,
        config: Any | None,
        *,
        filter: Any = None,
        before: Any = None,
        limit: Any = None,
    ) -> Any:
        async for item in self.inner.alist(config, filter=filter, before=before, limit=limit):
            yield item

    # ── Async write paths (redact) ─────────────────────────────────────────
    async def aput(
        self,
        config: Any,
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: Any,
    ) -> Any:
        self._redaction_count += 1
        return await self.inner.aput(
            config,
            self.redactor.redact(checkpoint),
            self.redactor.redact(metadata),
            new_versions,
        )

    async def aput_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._redaction_count += 1
        safe = [(ch, self.redactor.redact(v)) for ch, v in writes]
        return await self.inner.aput_writes(config, safe, task_id, task_path)

    @property
    def redaction_count(self) -> int:
        """Observability hook: how many writes were redacted (F-20-OBS1)."""
        return self._redaction_count
