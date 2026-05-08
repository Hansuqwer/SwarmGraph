"""Pluggable embedding providers for embedding-based anti-drift.

Three shipped adapters:
  - NullEmbedder        — returns []. Triggers fallback (used as a "disable" marker).
  - HashEmbedder        — deterministic hash-based pseudo-embeddings (32 dims).
                          Useful for tests + smoke runs without a real provider.
  - GatewayEmbedder     — calls an embeddings-capable adapter via the gateway
                          (e.g. openai_adapter.embed); only triggered when the
                          user provides one.

Swap any of these into SwarmConfig via `embedder=` constructor parameter or
the `swarm.llm.embeddings.set_default_embedder(...)` helper.

Cosine similarity helper included so callers don't pull in numpy.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Any, Iterable, Optional, Protocol


# ── Protocol ─────────────────────────────────────────────────────────────

class EmbeddingProvider(Protocol):
    """Anything callable in this shape is a valid embedder."""

    def embed(self, text: str) -> list[float]:
        """Return a vector representing `text`. Empty list = unsupported."""
        ...


# ── Null (disabled marker) ───────────────────────────────────────────────

class NullEmbedder:
    """Returns []. Caller treats as 'embeddings unavailable' and falls back."""

    def embed(self, text: str) -> list[float]:
        return []

    def __repr__(self) -> str:  # pragma: no cover
        return "NullEmbedder()"


# ── Hash-based deterministic pseudo-embedder ─────────────────────────────

class HashEmbedder:
    """Token-bag → SHA-256 → 32-float vector.

    Properties:
      - Deterministic: same text → same vector.
      - Fast: pure stdlib, no model load.
      - Bag-of-words: order-insensitive, which is desirable for short
        objective vs code-output comparisons (whitespace doesn't matter).
      - 32-dim: small enough to keep cosine-similarity cheap, large enough
        to give sane discrimination for swarm-scale corpora (~1000 entries).

    NOT a real semantic embedder. For production, plug in
    `GatewayEmbedder(provider_id="openai")` or your own that calls a real
    embeddings API.
    """

    DIMS = 32

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return []
        # Bag-of-words: lowercase, split, accumulate per-token hashes
        tokens = text.lower().split()
        if not tokens:
            return []
        accum = [0.0] * self.DIMS
        for tok in tokens:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            # 32 bytes → 32 unsigned bytes → centered ([-1, 1])
            for i in range(self.DIMS):
                accum[i] += (h[i] - 128) / 128.0
        # L2-normalise (so cosine = dot product)
        norm = math.sqrt(sum(x * x for x in accum))
        if norm == 0.0:
            return [0.0] * self.DIMS
        return [x / norm for x in accum]

    def __repr__(self) -> str:  # pragma: no cover
        return f"HashEmbedder(dims={self.DIMS})"


# ── Gateway-backed embedder ──────────────────────────────────────────────

class GatewayEmbedder:
    """Calls a registered gateway adapter's `embed` method.

    Lazy: the adapter is only loaded on first embed() call. If the adapter
    has no `embed` method (most LLM adapters don't), returns []. The caller
    then treats it as "unavailable" and falls back to keyword-mode drift.
    """

    def __init__(
        self,
        provider_id: str = "openai",
        model_id: str = "",
        adapter_factory: Optional[Any] = None,
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self._adapter_factory = adapter_factory
        self._adapter: Any = None
        self._adapter_resolved = False

    def _resolve_adapter(self) -> Any:
        if self._adapter_resolved:
            return self._adapter
        try:
            if self._adapter_factory is not None:
                self._adapter = self._adapter_factory(self.provider_id)
            else:
                from ai_provider_swarm_gateway.graph.nodes import _get_adapter  # type: ignore
                self._adapter = _get_adapter(self.provider_id)
        except Exception:
            self._adapter = None
        self._adapter_resolved = True
        return self._adapter

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return []
        adapter = self._resolve_adapter()
        if adapter is None:
            return []
        # Try a list of method names that gateway adapters may expose
        for name in ("embed", "embed_text", "embeddings", "embedding"):
            method = getattr(adapter, name, None)
            if not callable(method):
                continue
            try:
                kwargs: dict[str, Any] = {"text": text} if name == "embed_text" else {}
                if self.model_id:
                    kwargs["model"] = self.model_id
                # Try keyword form first
                try:
                    out = method(text, **kwargs) if not kwargs else method(**kwargs, text=text) if name == "embed" else method(text, **kwargs)
                except TypeError:
                    out = method(text)
                return list(out) if out else []
            except Exception:
                return []
        return []

    def __repr__(self) -> str:  # pragma: no cover
        return f"GatewayEmbedder(provider_id={self.provider_id!r})"


# ── Cosine similarity (no numpy) ─────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity ∈ [-1, 1]. Returns 0.0 for empty/mismatched dims."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Default embedder registry ────────────────────────────────────────────

_DEFAULT_EMBEDDER: EmbeddingProvider = NullEmbedder()


def set_default_embedder(embedder: EmbeddingProvider) -> None:
    """Set the process-wide default embedder.

    Used by `SwarmState.check_drift` when the SwarmConfig sets
    `anti_drift_mode="embedding"` but no embedder is bound elsewhere.
    """
    global _DEFAULT_EMBEDDER
    _DEFAULT_EMBEDDER = embedder


def get_default_embedder() -> EmbeddingProvider:
    return _DEFAULT_EMBEDDER


__all__ = [
    "EmbeddingProvider",
    "NullEmbedder",
    "HashEmbedder",
    "GatewayEmbedder",
    "cosine_similarity",
    "set_default_embedder",
    "get_default_embedder",
]
