"""SwarmMemory — patched.

F-12A: _index converted to PrivateAttr (was class-level mutable default with
       Pydantic field declaration ambiguity)
F-26A: export_jsonl / import_jsonl persistence
F-26B: promote_score preserves created_at via in-place replacement
F-26C: namespace-keyed search avoids full-list scan
F-26-CORR1: _cap() preserves insertion order (sorts a copy when evicting)
F-12-T1 / F-26-CORR2: model_validator runs initial cap
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from pydantic import Field, PrivateAttr, field_validator, model_validator

from .base import FrozenModel, HardenedModel, stable_hash


# ── SwarmMemoryEntry ───────────────────────────────────────────────────────

class SwarmMemoryEntry(FrozenModel):
    """A single stored insight/pattern."""
    key: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1, max_length=8192)
    namespace: str = Field(default="default", min_length=1, max_length=64)
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, max_length=32)
    source_agent_id: str = ""
    created_at: float = Field(default_factory=time.time)
    access_count: int = Field(default=0, ge=0)

    def entry_hash(self) -> str:
        return stable_hash(f"{self.namespace}:{self.key}:{self.value}")


# ── SwarmMemory ────────────────────────────────────────────────────────────

_MAX_ENTRIES = 1000


class SwarmMemory(HardenedModel):
    """In-process swarm memory with namespace isolation, keyword search, SONA."""
    entries: list[SwarmMemoryEntry] = Field(default_factory=list)
    max_entries: int = Field(default=_MAX_ENTRIES, ge=1, le=100_000)
    sona_min_score: float = Field(default=0.7, ge=0.0, le=1.0)

    # F-12A: PrivateAttr (was a regular field with mutable default)
    _index: dict[str, dict[str, SwarmMemoryEntry]] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _initial_cap_and_index(self) -> "SwarmMemory":
        # F-12-T1: enforce cap on construction (was only at store-time)
        self._cap()
        # F-12-LG1: rebuild index after capping
        self._rebuild_index()
        return self

    # ── Public API ─────────────────────────────────────────────────────────

    def store(
        self,
        key: str,
        value: str,
        *,
        namespace: str = "default",
        score: float = 1.0,
        tags: list[str] | None = None,
        source_agent_id: str = "",
        preserve_created_at: float | None = None,   # F-26B
    ) -> SwarmMemoryEntry:
        """Add or replace a memory entry."""
        entry_kwargs: dict[str, Any] = {
            "key": key,
            "value": value,
            "namespace": namespace,
            "score": score,
            "tags": tags or [],
            "source_agent_id": source_agent_id,
        }
        if preserve_created_at is not None:
            entry_kwargs["created_at"] = preserve_created_at
        entry = SwarmMemoryEntry(**entry_kwargs)
        # Remove old entry with same (key, namespace)
        self.entries = [
            e for e in self.entries
            if not (e.key == key and e.namespace == namespace)
        ]
        self.entries.append(entry)
        self._cap()
        self._rebuild_index()
        return entry

    def get(self, key: str, namespace: str = "default") -> SwarmMemoryEntry | None:
        return self._index.get(namespace, {}).get(key)

    def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SwarmMemoryEntry]:
        """Keyword search; weighted by entry score."""
        query_tokens = set(query.lower().split())

        # F-26C: use index when namespace is set
        if namespace is not None:
            candidates: Iterable[SwarmMemoryEntry] = self._index.get(namespace, {}).values()
        else:
            candidates = self.entries

        results: list[tuple[float, SwarmMemoryEntry]] = []
        for entry in candidates:
            if entry.score < min_score:
                continue
            value_tokens = set(entry.value.lower().split())
            key_tokens = set(entry.key.lower().replace("-", " ").split())
            union = query_tokens | value_tokens | key_tokens
            overlap = len(query_tokens & (value_tokens | key_tokens))
            sim = overlap / len(union) if union else 0.0
            weighted = sim * entry.score
            results.append((weighted, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:top_k]]

    def distill(self) -> list[SwarmMemoryEntry]:
        """SONA DISTILL: remove entries below sona_min_score."""
        kept, removed = [], []
        for e in self.entries:
            if e.score >= self.sona_min_score:
                kept.append(e)
            else:
                removed.append(e)
        self.entries = kept
        self._rebuild_index()
        return removed

    def promote_score(
        self,
        key: str,
        namespace: str = "default",
        delta: float = 0.05,
    ) -> None:
        """SONA CONSOLIDATE: boost score of accessed entry. Preserves created_at (F-26B)."""
        existing = self.get(key, namespace)
        if existing is None:
            return
        new_score = min(1.0, existing.score + delta)
        # F-26B: preserve original created_at
        self.store(
            key=existing.key,
            value=existing.value,
            namespace=existing.namespace,
            score=new_score,
            tags=existing.tags,
            source_agent_id=existing.source_agent_id,
            preserve_created_at=existing.created_at,
        )

    def namespace_entries(self, namespace: str) -> list[SwarmMemoryEntry]:
        return list(self._index.get(namespace, {}).values())

    def size(self) -> int:
        return len(self.entries)

    # ── Persistence (F-26A) ────────────────────────────────────────────────

    def export_jsonl(self, path: Path) -> int:
        """Append-only JSONL export of every entry. Returns count written."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for e in self.entries:
                fh.write(json.dumps(e.model_dump(mode="json")) + "\n")
        return len(self.entries)

    def import_jsonl(self, path: Path, *, replace: bool = False) -> int:
        """Load entries from JSONL. If replace=True, clears existing entries first."""
        path = Path(path)
        if not path.exists():
            return 0
        loaded: list[SwarmMemoryEntry] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                loaded.append(SwarmMemoryEntry.model_validate_json(line))
        if replace:
            self.entries = loaded
        else:
            # Merge: keep highest-score entry per (key, namespace)
            existing: dict[tuple[str, str], SwarmMemoryEntry] = {
                (e.key, e.namespace): e for e in self.entries
            }
            for e in loaded:
                k = (e.key, e.namespace)
                if k not in existing or e.score > existing[k].score:
                    existing[k] = e
            self.entries = list(existing.values())
        self._cap()
        self._rebuild_index()
        return len(loaded)

    # ── Internals ──────────────────────────────────────────────────────────

    def _rebuild_index(self) -> None:
        idx: dict[str, dict[str, SwarmMemoryEntry]] = defaultdict(dict)
        for e in self.entries:
            idx[e.namespace][e.key] = e
        self._index = dict(idx)

    def _cap(self) -> None:
        """F-26-CORR1: evict lowest-score entries while preserving order of survivors."""
        if len(self.entries) <= self.max_entries:
            return
        # Determine which entries to keep (top-N by score) without sorting in-place.
        scored = sorted(
            ((e.score, idx) for idx, e in enumerate(self.entries)),
            key=lambda x: (-x[0], x[1]),
        )
        keep_indices = {i for _, i in scored[: self.max_entries]}
        self.entries = [e for i, e in enumerate(self.entries) if i in keep_indices]


# ── Vector adapter (unchanged contract) ────────────────────────────────────

class VectorMemoryAdapter:
    """Optional HNSW/vector backend adapter."""

    def embed(self, text: str) -> list[float]:
        """Override to return real embeddings. Default: empty (triggers fallback)."""
        return []

    def search_vectors(
        self,
        query_embedding: list[float],
        entries: list[SwarmMemoryEntry],
        top_k: int = 5,
    ) -> list[SwarmMemoryEntry]:
        raise NotImplementedError("Plug in a vector backend to enable semantic search")


class HybridMemorySearch:
    """Combines SwarmMemory keyword + optional VectorMemoryAdapter."""

    def __init__(
        self,
        memory: SwarmMemory,
        adapter: VectorMemoryAdapter | None = None,
    ) -> None:
        self.memory = memory
        self.adapter = adapter

    def search(
        self,
        query: str,
        top_k: int = 5,
        namespace: str | None = None,
    ) -> list[SwarmMemoryEntry]:
        if self.adapter:
            try:
                embedding = self.adapter.embed(query)
                # F-26-CORR5: empty OR all-zero embedding triggers fallback
                if embedding and any(embedding):
                    candidates = (
                        self.memory.namespace_entries(namespace)
                        if namespace
                        else self.memory.entries
                    )
                    return self.adapter.search_vectors(embedding, candidates, top_k)
            except NotImplementedError:
                pass
        return self.memory.search(query, namespace=namespace, top_k=top_k)


__all__ = [
    "SwarmMemoryEntry",
    "SwarmMemory",
    "VectorMemoryAdapter",
    "HybridMemorySearch",
]
