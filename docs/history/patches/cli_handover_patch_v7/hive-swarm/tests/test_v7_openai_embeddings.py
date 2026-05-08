"""Tests for OpenAIEmbeddingAdapter — no live network."""
from __future__ import annotations

import json
import os

import pytest

from swarm.llm.embeddings import (
    HashEmbedder,
    NullEmbedder,
    OpenAIEmbeddingAdapter,
    _OPENAI_KEY_ENV_ALIASES,
    default_embedder_from_env,
)


# ── Fake HTTP client ─────────────────────────────────────────────────────

class _FakeHttp:
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        self.calls: list[dict] = []

    def post_json(self, url, payload, *, api_key, timeout):
        self.calls.append({"url": url, "payload": payload, "api_key": api_key})
        return self.status, self.body


# ── Configuration ────────────────────────────────────────────────────────

def test_unconfigured_without_any_key(monkeypatch):
    for name in _OPENAI_KEY_ENV_ALIASES:
        monkeypatch.delenv(name, raising=False)
    a = OpenAIEmbeddingAdapter()
    assert a.is_configured() is False


def test_configured_with_explicit_key():
    a = OpenAIEmbeddingAdapter(api_key="explicit-key")
    assert a.is_configured() is True


def test_configured_with_env_key(monkeypatch):
    for name in _OPENAI_KEY_ENV_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    a = OpenAIEmbeddingAdapter()
    assert a.is_configured() is True


def test_alias_envvar_works(monkeypatch):
    for name in _OPENAI_KEY_ENV_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_PROVIDER_OPENAI_API_KEY", "alias-key")
    a = OpenAIEmbeddingAdapter()
    assert a.is_configured() is True


# ── Embed happy path ─────────────────────────────────────────────────────

_FAKE_EMBEDDING = [0.01, 0.02, 0.03, -0.04, 0.5]
_FAKE_BODY = json.dumps({
    "data": [{"embedding": _FAKE_EMBEDDING, "index": 0}],
    "model": "text-embedding-3-small",
    "usage": {"prompt_tokens": 5, "total_tokens": 5},
})


def test_embed_returns_vector_on_200():
    http = _FakeHttp(200, _FAKE_BODY)
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=http)
    out = a.embed("hello world")
    assert out == _FAKE_EMBEDDING


def test_embed_sends_correct_payload():
    http = _FakeHttp(200, _FAKE_BODY)
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=http, model="text-embedding-3-large")
    a.embed("hello")
    assert http.calls[0]["payload"] == {"model": "text-embedding-3-large", "input": "hello"}
    assert http.calls[0]["api_key"] == "k"


# ── Embed failure modes — all return [] for keyword fallback ────────────

def test_embed_returns_empty_when_no_key(monkeypatch):
    for name in _OPENAI_KEY_ENV_ALIASES:
        monkeypatch.delenv(name, raising=False)
    a = OpenAIEmbeddingAdapter()
    assert a.embed("text") == []


def test_embed_returns_empty_for_blank_text():
    a = OpenAIEmbeddingAdapter(api_key="k")
    assert a.embed("") == []
    assert a.embed("   ") == []


def test_embed_returns_empty_on_4xx():
    http = _FakeHttp(401, '{"error": "invalid api key"}')
    a = OpenAIEmbeddingAdapter(api_key="bad", http_client=http)
    assert a.embed("text") == []


def test_embed_returns_empty_on_5xx():
    http = _FakeHttp(503, "")
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=http)
    assert a.embed("text") == []


def test_embed_returns_empty_on_invalid_json():
    http = _FakeHttp(200, "not-json-{")
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=http)
    assert a.embed("text") == []


def test_embed_returns_empty_on_missing_data_field():
    http = _FakeHttp(200, '{"object": "list"}')
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=http)
    assert a.embed("text") == []


def test_embed_returns_empty_on_missing_embedding_field():
    http = _FakeHttp(200, '{"data": [{"index": 0}]}')
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=http)
    assert a.embed("text") == []


def test_embed_returns_empty_on_non_list_embedding():
    http = _FakeHttp(200, '{"data": [{"embedding": "wrong"}]}')
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=http)
    assert a.embed("text") == []


def test_embed_returns_empty_on_connection_error():
    class BoomHttp:
        def post_json(self, *a, **kw):
            raise ConnectionError("network down")
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=BoomHttp())
    assert a.embed("text") == []


def test_embed_returns_empty_on_unexpected_exception():
    class BoomHttp:
        def post_json(self, *a, **kw):
            raise ValueError("simulated boom")
    a = OpenAIEmbeddingAdapter(api_key="k", http_client=BoomHttp())
    assert a.embed("text") == []


# ── default_embedder_from_env ────────────────────────────────────────────

def test_default_embedder_picks_openai_when_key_present(monkeypatch):
    for name in _OPENAI_KEY_ENV_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    e = default_embedder_from_env()
    assert isinstance(e, OpenAIEmbeddingAdapter)


def test_default_embedder_picks_hash_when_no_key(monkeypatch):
    for name in _OPENAI_KEY_ENV_ALIASES:
        monkeypatch.delenv(name, raising=False)
    e = default_embedder_from_env()
    assert isinstance(e, HashEmbedder)


def test_default_embedder_picks_openai_via_alias(monkeypatch):
    for name in _OPENAI_KEY_ENV_ALIASES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_PROVIDER_OPENAI_API_KEY", "alias-k")
    e = default_embedder_from_env()
    assert isinstance(e, OpenAIEmbeddingAdapter)


# ── Integration with check_drift (embedding mode) ───────────────────────

def test_openai_embedder_used_via_set_default(monkeypatch):
    """OpenAIEmbeddingAdapter as the process default — drift check works."""
    from swarm.llm.embeddings import set_default_embedder
    from swarm.models.config import SwarmConfig
    from swarm.models.state import SwarmState

    http = _FakeHttp(200, _FAKE_BODY)
    adapter = OpenAIEmbeddingAdapter(api_key="k", http_client=http)
    set_default_embedder(adapter)
    try:
        cfg = SwarmConfig(
            anti_drift_enabled=True,
            anti_drift_mode="embedding",
            anti_drift_similarity_threshold=0.1,
        )
        s = SwarmState(swarm_id="s1", objective="implement OAuth", config=cfg)
        # Both texts get the same fake embedding → cosine = 1.0 → passes
        assert s.check_drift("anything") is True
    finally:
        set_default_embedder(NullEmbedder())
