"""Unit tests for NineRouterAdapter.

No live localhost dependency: the HTTP layer is mocked via a fake
_HttpClient passed into the adapter constructor.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from ai_provider_swarm_gateway.providers.nine_router_adapter import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    NineRouterAdapter,
    NineRouterResponse,
    _extract_content,
    _parse_quirky_body,
    _resolve_api_key,
    _validate_http_url,
)

# ── Fake HTTP transport ──────────────────────────────────────────────────


class FakeHttpClient:
    """Records the request, returns a scripted response."""

    def __init__(self, status: int, body: str, headers: dict | None = None):
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.calls: list[dict[str, Any]] = []

    def post_json(self, url, payload, *, api_key, timeout, extra_headers=None):
        self.calls.append(
            {
                "url": url,
                "payload": payload,
                "api_key": api_key,
                "timeout": timeout,
                "extra_headers": dict(extra_headers or {}),
            }
        )
        return self.status, self.body, self.headers


# ── Parser quirk ─────────────────────────────────────────────────────────


def test_parse_strips_trailing_data_done():
    body = (
        '{"id": "x", "model": "kc/kilo-auto/free", '
        '"choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}]}'
        "\n\ndata: [DONE]\n"
    )
    data = _parse_quirky_body(body)
    assert data["choices"][0]["message"]["content"] == "pong"


def test_parse_no_sentinel_works():
    body = '{"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}'
    data = _parse_quirky_body(body)
    assert data["choices"][0]["message"]["content"] == "hi"


def test_parse_data_in_string_is_not_truncated_prematurely():
    """The 'data:' marker is only honoured when at the start of a line."""
    body = (
        '{"choices": [{"message": {"content": "the data: from server"}, "finish_reason": "stop"}]}'
        "\ndata: [DONE]"
    )
    data = _parse_quirky_body(body)
    assert "the data: from server" in data["choices"][0]["message"]["content"]


def test_parse_empty_body_raises():
    with pytest.raises(ValueError):
        _parse_quirky_body("")


def test_parse_only_sentinel_raises():
    with pytest.raises(ValueError):
        _parse_quirky_body("data: [DONE]")


# ── Content extraction (three-level fallback) ────────────────────────────


def test_extract_content_primary():
    data = {"choices": [{"message": {"content": "main"}, "finish_reason": "stop"}]}
    content, fr = _extract_content(data)
    assert content == "main"
    assert fr == "stop"


def test_extract_content_falls_back_to_reasoning():
    data = {
        "choices": [
            {
                "message": {"content": "", "reasoning": "thinking out loud"},
                "finish_reason": None,
            }
        ]
    }
    content, fr = _extract_content(data)
    assert content == "thinking out loud"
    assert fr == "reasoning_only"


def test_extract_content_falls_back_to_legacy_text():
    data = {"choices": [{"text": "old completion shape", "finish_reason": "stop"}]}
    content, fr = _extract_content(data)
    assert content == "old completion shape"


def test_extract_content_all_empty_raises():
    data = {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
    with pytest.raises(ValueError):
        _extract_content(data)


def test_extract_content_no_choices_raises():
    with pytest.raises(ValueError):
        _extract_content({"choices": []})


# ── API-key resolution + aliases ─────────────────────────────────────────


def test_explicit_key_wins(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_9ROUTER_API_KEY", "from-env")
    assert _resolve_api_key("explicit") == "explicit"


def test_resolves_from_primary_env(monkeypatch):
    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_9ROUTER_API_KEY", "primary-value")
    assert _resolve_api_key() == "primary-value"


def test_alias_router_api_key(monkeypatch):
    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ROUTER_API_KEY", "via-router-alias")
    assert _resolve_api_key() == "via-router-alias"


def test_alias_kilo_code(monkeypatch):
    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KILO_CODE_API_KEY", "via-kilo")
    assert _resolve_api_key() == "via-kilo"


def test_alias_openai_fallback(monkeypatch):
    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-fallback")
    assert _resolve_api_key() == "openai-fallback"


def test_no_key_returns_none(monkeypatch):
    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert _resolve_api_key() is None


# ── Adapter construction + defaults ──────────────────────────────────────


def test_adapter_defaults(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("AI_PROVIDER_GATEWAY_9ROUTER_MODEL", raising=False)
    a = NineRouterAdapter()
    assert a.base_url == DEFAULT_BASE_URL
    assert a.model == DEFAULT_MODEL
    assert a.endpoint == DEFAULT_BASE_URL + "/chat/completions"


def test_adapter_env_overrides(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL", "https://router.example/v1/")
    monkeypatch.setenv("AI_PROVIDER_GATEWAY_9ROUTER_MODEL", "custom/model")
    a = NineRouterAdapter()
    assert a.base_url == "https://router.example/v1"
    assert a.model == "custom/model"


def test_validate_base_url_allows_local_http_and_remote_https():
    assert _validate_http_url("http://localhost:20128/v1") == "http://localhost:20128/v1"
    assert _validate_http_url("http://127.0.0.1:20128/v1") == "http://127.0.0.1:20128/v1"
    assert _validate_http_url("https://router.example/v1") == "https://router.example/v1"


def test_validate_base_url_rejects_remote_http():
    with pytest.raises(ValueError, match="HTTPS"):
        _validate_http_url("http://example.com/v1")


def test_is_configured_true_with_explicit_key():
    a = NineRouterAdapter(api_key="explicit-key")
    assert a.is_configured() is True


def test_is_configured_false_without_key(monkeypatch):
    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    a = NineRouterAdapter()
    assert a.is_configured() is False


# ── End-to-end happy path ────────────────────────────────────────────────

PONG_BODY = (
    '{"id": "chatcmpl-1", "model": "stepfun/step-3.5-flash:free", '
    '"choices": [{"message": {"role": "assistant", "content": "pong"}, '
    '"finish_reason": "stop"}], '
    '"usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9}}'
    "\n\ndata: [DONE]\n"
)


def test_chat_returns_normalised_response():
    fake = FakeHttpClient(status=200, body=PONG_BODY)
    a = NineRouterAdapter(api_key="test-key", http_client=fake)
    resp = a.chat(prompt="Say only pong.")
    assert isinstance(resp, NineRouterResponse)
    assert resp.content == "pong"
    assert resp.model_actually_used == "stepfun/step-3.5-flash:free"
    assert resp.finish_reason == "stop"
    assert resp.input_tokens == 8
    assert resp.output_tokens == 1


def test_chat_sends_correct_payload():
    fake = FakeHttpClient(status=200, body=PONG_BODY)
    a = NineRouterAdapter(
        api_key="test-key",
        http_client=fake,
        model="kc/kilo-auto/free",
    )
    a.chat(prompt="Say only pong.", max_tokens=80, temperature=0.0)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["api_key"] == "test-key"
    payload = call["payload"]
    assert payload["model"] == "kc/kilo-auto/free"
    assert payload["messages"] == [{"role": "user", "content": "Say only pong."}]
    assert payload["max_tokens"] == 80
    assert payload["temperature"] == 0.0


def test_chat_accepts_message_list():
    fake = FakeHttpClient(status=200, body=PONG_BODY)
    a = NineRouterAdapter(api_key="k", http_client=fake)
    a.chat(
        messages=[
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "ping?"},
        ]
    )
    assert fake.calls[0]["payload"]["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "ping?"},
    ]


def test_chat_aliases_all_dispatch_to_same_logic():
    fake = FakeHttpClient(status=200, body=PONG_BODY)
    a = NineRouterAdapter(api_key="k", http_client=fake)
    for method_name in ("chat", "chat_completion", "complete", "call", "invoke"):
        method = getattr(a, method_name)
        resp = method(prompt="x")
        assert resp.content == "pong"
    assert len(fake.calls) == 5  # one per alias


def test_chat_without_api_key_raises(monkeypatch):
    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    fake = FakeHttpClient(status=200, body=PONG_BODY)
    a = NineRouterAdapter(http_client=fake)
    with pytest.raises(PermissionError, match="API key"):
        a.chat(prompt="x")


def test_chat_http_error_surfaces_with_preview():
    fake = FakeHttpClient(status=429, body='{"error": "rate limited"}')
    a = NineRouterAdapter(api_key="k", http_client=fake)
    with pytest.raises(RuntimeError, match="429"):
        a.chat(prompt="x")


def test_chat_handles_reasoning_only_response():
    """Some 9router models stream only `reasoning`, leaving content empty."""
    body = (
        '{"choices": [{"message": {"content": "", "reasoning": "I think 4."}, '
        '"finish_reason": "stop"}]}\ndata: [DONE]'
    )
    fake = FakeHttpClient(status=200, body=body)
    a = NineRouterAdapter(api_key="k", http_client=fake)
    resp = a.chat(prompt="2+2?")
    assert resp.content == "I think 4."
    assert resp.finish_reason in ("stop", "reasoning_only")


def test_supports_capabilities():
    a = NineRouterAdapter(api_key="k")
    assert a.supports("chat") is True
    assert a.supports("code") is True
    assert a.supports("embeddings") is False
    assert a.supports("image") is False
