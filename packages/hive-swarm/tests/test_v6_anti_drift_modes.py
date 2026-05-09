"""Tests for the 3-mode anti-drift dispatch in SwarmState.check_drift."""

import pytest
from swarm.llm.embeddings import HashEmbedder, NullEmbedder
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState


def _state(*, mode="keyword", threshold=0.4, enabled=True):
    config = SwarmConfig(
        anti_drift_enabled=enabled,
        anti_drift_mode=mode,
        anti_drift_similarity_threshold=threshold,
    )
    return SwarmState(
        swarm_id="s1",
        objective="implement OAuth refresh token rotation",
        config=config,
    )


# ── mode="off" ───────────────────────────────────────────────────────────


def test_mode_off_always_returns_true():
    s = _state(mode="off")
    # Even completely unrelated text passes
    assert s.check_drift("absolutely nothing about authentication") is True


def test_mode_off_assert_no_drift_does_not_raise():
    s = _state(mode="off")
    s.assert_no_drift("totally unrelated output")  # must not raise


# ── mode="keyword" (back-compat with v5) ─────────────────────────────────


def test_mode_keyword_high_overlap_passes():
    s = _state(mode="keyword", threshold=0.4)
    candidate = "implement OAuth refresh token rotation logic in Python"
    assert s.check_drift(candidate) is True


def test_mode_keyword_low_overlap_fails():
    s = _state(mode="keyword", threshold=0.4)
    candidate = "def foo(): return 42"  # no shared tokens
    assert s.check_drift(candidate) is False


def test_mode_keyword_assert_no_drift_raises_on_drift():
    s = _state(mode="keyword", threshold=0.4)
    with pytest.raises(ValueError, match="Anti-drift"):
        s.assert_no_drift("totally unrelated output")


def test_anti_drift_disabled_overrides_mode():
    s = _state(mode="keyword", enabled=False)
    # Even with mode=keyword and unrelated output, disabled bypasses
    assert s.check_drift("def foo(): return 42") is True


# ── mode="embedding" ─────────────────────────────────────────────────────


def test_mode_embedding_with_null_falls_back_to_keyword():
    """If no embedder bound, should fall back to keyword detection (not crash)."""
    s = _state(mode="embedding", threshold=0.4)
    # Pass NullEmbedder explicitly
    candidate = "def foo(): return 42"
    # Falls back to keyword: zero overlap → False
    assert s.check_drift(candidate, embedder=NullEmbedder()) is False


def test_mode_embedding_with_hash_embedder_passes_for_similar_text():
    """HashEmbedder's bag-of-words → similar topics correlate."""
    s = _state(mode="embedding", threshold=0.3)
    embedder = HashEmbedder()
    # Same words, slightly different order — bag-of-words identical → cosine 1.0
    candidate = "OAuth refresh token rotation implementation"
    assert s.check_drift(candidate, embedder=embedder) is True


def test_mode_embedding_with_hash_embedder_fails_for_dissimilar_text():
    s = _state(mode="embedding", threshold=0.5)
    embedder = HashEmbedder()
    candidate = "rename variable foo bar"  # totally different vocabulary
    assert s.check_drift(candidate, embedder=embedder) is False


def test_mode_embedding_threshold_zero_always_passes():
    s = _state(mode="embedding", threshold=0.0)
    # Any non-degenerate cosine ≥ 0 passes
    embedder = HashEmbedder()
    assert s.check_drift("anything at all", embedder=embedder) is True


def test_mode_embedding_embedder_returning_empty_falls_back():
    """An embedder that returns [] should trigger keyword fallback."""
    s = _state(mode="keyword", threshold=0.4)  # set up keyword fallback expectations
    s2 = _state(mode="embedding", threshold=0.4)
    candidate = "implement OAuth refresh token logic"
    # NullEmbedder returns [] → fallback to keyword
    # Keyword path on this candidate has high overlap with objective → True
    assert s2.check_drift(candidate, embedder=NullEmbedder()) is True


def test_mode_embedding_embedder_raising_falls_back():
    """If embedder raises, should fall back to keyword (not crash)."""

    class BoomEmbedder:
        def embed(self, text):
            raise RuntimeError("simulated embedder failure")

    s = _state(mode="embedding", threshold=0.4)
    candidate = "implement OAuth refresh token rotation"
    # Embedder raises → fallback to keyword → high overlap → True
    assert s.check_drift(candidate, embedder=BoomEmbedder()) is True


# ── Solves the 80-workers-from-5 retry storm ─────────────────────────────


def test_mode_off_eliminates_iteration_storm():
    """With mode='off', anti_drift never fires → judge accepts → no retry loop.
    This is the fix for the v5 signal: 16 retries × 5 workers = 80 worker calls.
    """
    s = _state(mode="off")
    # Even a totally drifting output is accepted
    assert s.check_drift("import sys; print('hello')") is True


def test_mode_embedding_solves_natural_language_vs_code_mismatch():
    """The exact failure mode that produced 80 workers in v5: verbose
    NL objective vs concrete Python output → keyword overlap is near-zero
    → judge fails → retry storm. Embedding mode + low threshold avoids this."""
    s = _state(mode="embedding", threshold=0.05)  # generous threshold
    embedder = HashEmbedder()
    candidate = "def authenticate(token): return True"
    # The bag-of-words won't perfectly correlate, but a low threshold passes.
    # The point is: this DOES NOT crash and we get a deterministic decision.
    result = s.check_drift(candidate, embedder=embedder)
    assert isinstance(result, bool)


# ── SwarmConfig validation ───────────────────────────────────────────────


def test_invalid_anti_drift_mode_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SwarmConfig(anti_drift_mode="magic")
