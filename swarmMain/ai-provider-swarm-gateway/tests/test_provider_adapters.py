"""Tests for provider adapters — mock, stubs, credential checks."""
from __future__ import annotations
import os
import pytest
from src.ai_provider_swarm_gateway.providers.mock_adapter import MockAdapter
from src.ai_provider_swarm_gateway.providers.openai_adapter import OpenAIAdapter
from src.ai_provider_swarm_gateway.providers.groq_adapter import GroqAdapter
from src.ai_provider_swarm_gateway.providers.google_adapter import GoogleAdapter


class TestMockAdapter:
    def test_always_configured(self):
        adapter = MockAdapter()
        assert adapter.is_configured() is True

    def test_returns_deterministic_response(self):
        adapter = MockAdapter()
        r = adapter.call("Hello")
        assert r.content is not None
        assert "[MOCK]" in r.content
        assert r.error is None

    def test_simulates_failure(self):
        adapter = MockAdapter(simulate_failure=True, failure_message="Test failure")
        r = adapter.call("Hello")
        assert r.error == "Test failure"
        assert r.content is None

    def test_increments_call_count(self):
        adapter = MockAdapter()
        adapter.call("a")
        adapter.call("b")
        assert adapter._call_count == 2

    def test_reset_clears_count(self):
        adapter = MockAdapter()
        adapter.call("a")
        adapter.reset()
        assert adapter._call_count == 0

    def test_tokens_used_estimated(self):
        adapter = MockAdapter()
        r = adapter.call("one two three four five")
        assert r.tokens_used > 0

    def test_provider_id_correct(self):
        adapter = MockAdapter()
        r = adapter.call("hello")
        assert r.provider_id == "mock"


class TestRealAdapterStubs:
    """Real adapters must return not-configured response when env var is absent."""

    def _clear_env(self, var: str):
        os.environ.pop(var, None)

    def test_openai_not_configured_without_key(self):
        self._clear_env("OPENAI_API_KEY")
        adapter = OpenAIAdapter()
        assert adapter.is_configured() is False
        r = adapter.call("hello")
        assert r.error is not None
        assert "not configured" in r.error.lower()

    def test_groq_not_configured_without_key(self):
        self._clear_env("GROQ_API_KEY")
        adapter = GroqAdapter()
        assert adapter.is_configured() is False
        r = adapter.call("hello")
        assert r.error is not None

    def test_google_not_configured_without_key(self):
        self._clear_env("GOOGLE_API_KEY")
        adapter = GoogleAdapter()
        assert adapter.is_configured() is False
        r = adapter.call("hello")
        assert r.error is not None
