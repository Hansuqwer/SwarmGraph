"""
AGENT 26 — Memory Model Specialist
AGENT 27 — SONA Loop Specialist
AGENT 28 — Vector Memory Adapter Specialist

SwarmMemoryEntry, SwarmMemory with namespace isolation, SONA loop, keyword fallback.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel, HardenedModel, stable_hash


# ---------------------------------------------------------------------------
# SwarmMemoryEntry — one stored pattern
# ---------------------------------------------------------------------------

class SwarmMemoryEntry(FrozenModel):
    """
    A single stored insight/pattern in SwarmMemory.
    Immutable after creation (frozen=True).
    Ruflo equivalent: memory store --key K --value V --namespace N
    """
    key: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1, max_length=8192)
    namespace: str = Field(default="default", min_length=1, max_length=64)
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    source_agent_id: str = ""
    created_at: float = Field(default_factory=time.time)
    access_count: int = Field(default=0, ge=0)

    def entry_hash(self) -> str:
        return stable_hash(f"{self.namespace}:{self.key}:{self.value}")


# ---------------------------------------------------------------------------
# SwarmMemory — the in-process memory store (SONA-ready)
# ---------------------------------------------------------------------------

_MAX_ENTRIES = 1000


class SwarmMemory(HardenedModel):
    """
    In-process swarm memory with:
    - Namespace isolation
    - Keyword-based search (always available)
    - Optional vector backend (pluggable via adapter)
    - SONA distillation: prune low-score entries
    - Bounded to _MAX_ENTRIES

    Ruflo equivalents:
      memory_store()   → store()
      memory_search()  → search()
      distill_node()   → distill()
    """
    entries: list[SwarmMemoryEntry] = Field(default_factory=list)
    max_entries: int = Field(default=_MAX_ENTRIES, ge=10, le=100_000)
    sona_min_score: float = Field(default=0.7, ge=0.0, le=1.0)
    _index: dict[str, dict[str, SwarmMemoryEntry]] = {}   # namespace → key → entry

    @model_validator(mode="after")
    def _rebuild_index(self) -> "SwarmMemory":
        idx: dict[str, dict[str, SwarmMemoryEntry]] = defaultdict(dict)
        for e in self.entries:
            idx[e.namespace][e.key] = e
        object.__setattr__(self, "_index", idx)
        return self

    # --- Public API ---

    def store(
        self,
        key: str,
        value: str,
        *,
        namespace: str = "default",
        score: float = 1.0,
        tags: list[str] | None = None,
        source_agent_id: str = "",
    ) -> SwarmMemoryEntry:
        """
        Add or replace a memory entry.
        Ruflo: memory store --key K --value V --namespace N
        """
        entry = SwarmMemoryEntry(
            key=key,
            value=value,
            namespace=namespace,
            score=score,
            tags=tags or [],
            source_agent_id=source_agent_id,
        )
        # Remove old entry with same key in namespace if present
        self.entries = [
            e for e in self.entries
            if not (e.key == key and e.namespace == namespace)
        ]
        self.entries.append(entry)
        self._cap()
        self._rebuild_index()
        return entry

    def get(self, key: str, namespace: str = "default") -> SwarmMemoryEntry | None:
        """Exact key lookup."""
        return self._index.get(namespace, {}).get(key)

    def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[SwarmMemoryEntry]:
        """
        Keyword search across entries.
        Scores by token overlap (0–1). Falls back to this when no vector backend.
        Ruflo: memory search --query "..."
        """
        query_tokens = set(query.lower().split())
        results: list[tuple[float, SwarmMemoryEntry]] = []
        for entry in self.entries:
            if namespace and entry.namespace != namespace:
                continue
            if entry.score < min_score:
                continue
            value_tokens = set(entry.value.lower().split())
            key_tokens = set(entry.key.lower().replace("-", " ").split())
            overlap = len(query_tokens & (value_tokens | key_tokens))
            total = len(query_tokens | value_tokens | key_tokens)
            sim = overlap / total if total > 0 else 0.0
            # Weight by stored entry score
            weighted = sim * entry.score
            results.append((weighted, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:top_k]]

    def distill(self) -> list[SwarmMemoryEntry]:
        """
        SONA DISTILL step: remove low-confidence entries.
        Keeps entries with score >= sona_min_score.
        Returns removed entries for logging.
        """
        kept, removed = [], []
        for e in self.entries:
            if e.score >= self.sona_min_score:
                kept.append(e)
            else:
                removed.append(e)
        self.entries = kept
        self._rebuild_index()
        return removed

    def promote_score(self, key: str, namespace: str = "default", delta: float = 0.05) -> None:
        """
        SONA CONSOLIDATE: boost score of a successfully accessed entry.
        Prevents catastrophic forgetting of high-value patterns (Ruflo: EWC++).
        """
        existing = self.get(key, namespace)
        if existing:
            new_score = min(1.0, existing.score + delta)
            self.store(
                key=existing.key,
                value=existing.value,
                namespace=existing.namespace,
                score=new_score,
                tags=existing.tags,
                source_agent_id=existing.source_agent_id,
            )

    def namespace_entries(self, namespace: str) -> list[SwarmMemoryEntry]:
        return list(self._index.get(namespace, {}).values())

    def size(self) -> int:
        return len(self.entries)

    # --- Internals ---

    def _cap(self) -> None:
        """Enforce max_entries by evicting lowest-score entries."""
        if len(self.entries) > self.max_entries:
            self.entries.sort(key=lambda e: e.score, reverse=True)
            self.entries = self.entries[: self.max_entries]


# ---------------------------------------------------------------------------
# Vector adapter stub (Agent 28)
# ---------------------------------------------------------------------------

class VectorMemoryAdapter:
    """
    Optional HNSW/vector backend adapter.
    Plug in any vector store (chromadb, hnswlib, faiss) by subclassing.
    Falls back to SwarmMemory keyword search when unavailable.

    Ruflo equivalent: AgentDB + HNSW 150x faster search.
    """

    def embed(self, text: str) -> list[float]:
        """Override to return real embeddings. Default: empty (triggers fallback)."""
        return []

    def search_vectors(
        self,
        query_embedding: list[float],
        entries: list[SwarmMemoryEntry],
        top_k: int = 5,
    ) -> list[SwarmMemoryEntry]:
        """Override to use HNSW/ANN search. Default: not implemented → fallback."""
        raise NotImplementedError("Plug in a vector backend to enable semantic search")


class HybridMemorySearch:
    """
    Combines SwarmMemory keyword search with an optional VectorMemoryAdapter.
    Uses vector search when available; keyword fallback otherwise.
    """

    def __init__(self, memory: SwarmMemory, adapter: VectorMemoryAdapter | None = None) -> None:
        self.memory = memory
        self.adapter = adapter

    def search(self, query: str, top_k: int = 5, namespace: str | None = None) -> list[SwarmMemoryEntry]:
        if self.adapter:
            try:
                embedding = self.adapter.embed(query)
                if embedding:
                    candidates = (
                        self.memory.namespace_entries(namespace)
                        if namespace
                        else self.memory.entries
                    )
                    return self.adapter.search_vectors(embedding, candidates, top_k)
            except NotImplementedError:
                pass
        # Keyword fallback
        return self.memory.search(query, namespace=namespace, top_k=top_k)
