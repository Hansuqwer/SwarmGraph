"""Tests for swarm.llm.embeddings."""
import math

import pytest

from swarm.llm.embeddings import (
    GatewayEmbedder,
    HashEmbedder,
    NullEmbedder,
    cosine_similarity,
    get_default_embedder,
    set_default_embedder,
)


# ── Cosine similarity helper ─────────────────────────────────────────────

def test_cosine_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_opposite_vectors():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_empty_returns_zero():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0], []) == 0.0
    assert cosine_similarity([], []) == 0.0


def test_cosine_dim_mismatch_returns_zero():
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_cosine_zero_norm_returns_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


# ── NullEmbedder ─────────────────────────────────────────────────────────

def test_null_embedder_returns_empty():
    e = NullEmbedder()
    assert e.embed("anything") == []
    assert e.embed("") == []


# ── HashEmbedder ─────────────────────────────────────────────────────────

def test_hash_embedder_deterministic():
    e = HashEmbedder()
    v1 = e.embed("hello world")
    v2 = e.embed("hello world")
    assert v1 == v2


def test_hash_embedder_returns_32_dims():
    e = HashEmbedder()
    v = e.embed("any text here")
    assert len(v) == 32


def test_hash_embedder_normalised_to_unit_length():
    e = HashEmbedder()
    v = e.embed("the quick brown fox jumps over the lazy dog")
    norm = math.sqrt(sum(x * x for x in v))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_hash_embedder_distinct_texts_distinct_vectors():
    e = HashEmbedder()
    v1 = e.embed("implement OAuth refresh tokens")
    v2 = e.embed("rename foo to bar")
    # Should be different and not perfectly correlated
    sim = cosine_similarity(v1, v2)
    assert sim != 1.0


def test_hash_embedder_bag_of_words_order_insensitive():
    e = HashEmbedder()
    v1 = e.embed("alpha beta gamma")
    v2 = e.embed("gamma alpha beta")
    # Bag-of-words: identical
    assert v1 == v2


def test_hash_embedder_empty_returns_empty():
    e = HashEmbedder()
    assert e.embed("") == []
    assert e.embed("   ") == []


def test_hash_embedder_similar_topics_correlate_above_random():
    """Sanity: texts about the same topic correlate higher than random pairs."""
    e = HashEmbedder()
    auth_a = e.embed("OAuth authentication refresh tokens")
    auth_b = e.embed("OAuth refresh token authentication flow")
    auth_unrelated = e.embed("rename variable foo bar typo")
    sim_related = cosine_similarity(auth_a, auth_b)
    sim_unrelated = cosine_similarity(auth_a, auth_unrelated)
    # Related should be higher than unrelated
    assert sim_related > sim_unrelated


# ── GatewayEmbedder ──────────────────────────────────────────────────────

def test_gateway_embedder_falls_back_when_adapter_missing():
    """If adapter_factory raises or has no embed, returns []."""
    def boom(pid):
        raise RuntimeError("no such adapter")
    e = GatewayEmbedder(adapter_factory=boom)
    assert e.embed("text") == []


def test_gateway_embedder_falls_back_when_adapter_has_no_embed():
    class NoEmbed:
        pass
    e = GatewayEmbedder(adapter_factory=lambda pid: NoEmbed())
    assert e.embed("text") == []


def test_gateway_embedder_uses_embed_method():
    class FakeAdapter:
        def embed(self, text):
            return [0.1, 0.2, 0.3]
    e = GatewayEmbedder(adapter_factory=lambda pid: FakeAdapter())
    assert e.embed("text") == [0.1, 0.2, 0.3]


def test_gateway_embedder_caches_adapter():
    calls: list[str] = []
    class FakeAdapter:
        def embed(self, text):
            return [0.0]
    def factory(pid):
        calls.append(pid)
        return FakeAdapter()
    e = GatewayEmbedder(provider_id="x", adapter_factory=factory)
    e.embed("a")
    e.embed("b")
    e.embed("c")
    assert len(calls) == 1   # cached after first lookup


# ── Default embedder registry ────────────────────────────────────────────

def test_default_embedder_is_null_initially():
    # Reset to ensure clean state
    set_default_embedder(NullEmbedder())
    assert isinstance(get_default_embedder(), NullEmbedder)


def test_set_default_embedder_swaps_global():
    try:
        set_default_embedder(HashEmbedder())
        assert isinstance(get_default_embedder(), HashEmbedder)
    finally:
        set_default_embedder(NullEmbedder())  # restore for other tests
