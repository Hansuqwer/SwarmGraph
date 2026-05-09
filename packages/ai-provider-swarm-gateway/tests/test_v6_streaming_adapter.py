"""Tests for NineRouterAdapter.chat_stream — no live network."""

import pytest

from ai_provider_swarm_gateway.providers.nine_router_adapter import (
    NineRouterAdapter,
    _parse_sse_data_line,
    _stream_event_to_chunk,
)


# ── _parse_sse_data_line ─────────────────────────────────────────────────


def test_parse_data_line_with_json():
    line = 'data: {"choices": [{"delta": {"content": "hi"}}]}'
    event = _parse_sse_data_line(line)
    assert event is not None
    assert event["choices"][0]["delta"]["content"] == "hi"


def test_parse_done_sentinel_returns_none():
    assert _parse_sse_data_line("data: [DONE]") is None


def test_parse_non_data_line_returns_none():
    assert _parse_sse_data_line("event: ping") is None
    assert _parse_sse_data_line("") is None
    assert _parse_sse_data_line(":") is None


def test_parse_data_line_invalid_json_returns_none():
    assert _parse_sse_data_line("data: not-json-{") is None


def test_parse_data_line_with_leading_whitespace():
    line = 'data:    {"choices": [{"delta": {"content": "x"}}]}'
    event = _parse_sse_data_line(line)
    assert event is not None


# ── _stream_event_to_chunk ───────────────────────────────────────────────


def test_event_to_chunk_extracts_content():
    event = {"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}
    chunk = _stream_event_to_chunk(event)
    assert chunk["delta"] == "hello"
    assert chunk["finish_reason"] == ""


def test_event_to_chunk_extracts_finish_reason():
    event = {"choices": [{"delta": {"content": "."}, "finish_reason": "stop"}]}
    chunk = _stream_event_to_chunk(event)
    assert chunk["finish_reason"] == "stop"


def test_event_to_chunk_falls_back_to_reasoning():
    event = {"choices": [{"delta": {"reasoning": "thinking"}, "finish_reason": None}]}
    chunk = _stream_event_to_chunk(event)
    assert chunk["delta"] == "thinking"


def test_event_to_chunk_handles_no_choices():
    chunk = _stream_event_to_chunk({})
    assert chunk["delta"] == ""
    assert chunk["finish_reason"] == ""


# ── chat_stream end-to-end with mocked HTTP ──────────────────────────────


class _FakeStreamingHttp:
    """Yields canned SSE lines."""

    def __init__(self, lines):
        self.lines = lines
        self.calls: list[dict] = []

    def post_json(self, *a, **kw):
        # Not used in stream tests; return non-streaming dummy
        return 200, "{}", {}

    def post_json_stream(self, url, payload, *, api_key, timeout):
        self.calls.append({"url": url, "payload": payload, "api_key": api_key})
        for line in self.lines:
            yield line


def test_chat_stream_yields_chunks():
    http = _FakeStreamingHttp(
        lines=[
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"!"},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
    )
    adapter = NineRouterAdapter(api_key="test-key", http_client=http)
    chunks = list(adapter.chat_stream(prompt="say hi"))
    assert [c["delta"] for c in chunks] == ["Hello", " world", "!"]
    assert chunks[-1]["finish_reason"] == "stop"


def test_chat_stream_skips_pings_and_done():
    http = _FakeStreamingHttp(
        lines=[
            "",
            ": ping",
            'data: {"choices":[{"delta":{"content":"x"},"finish_reason":null}]}',
            "data: [DONE]",
        ]
    )
    adapter = NineRouterAdapter(api_key="k", http_client=http)
    chunks = list(adapter.chat_stream(prompt="hi"))
    assert len(chunks) == 1
    assert chunks[0]["delta"] == "x"


def test_chat_stream_sends_stream_true_in_payload():
    http = _FakeStreamingHttp(lines=["data: [DONE]"])
    adapter = NineRouterAdapter(api_key="k", http_client=http)
    list(adapter.chat_stream(prompt="hi"))
    assert http.calls[0]["payload"]["stream"] is True


def test_chat_stream_passes_messages_correctly():
    http = _FakeStreamingHttp(lines=["data: [DONE]"])
    adapter = NineRouterAdapter(api_key="k", http_client=http)
    list(
        adapter.chat_stream(
            messages=[
                {"role": "system", "content": "be terse"},
                {"role": "user", "content": "ping?"},
            ]
        )
    )
    assert http.calls[0]["payload"]["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "ping?"},
    ]


def test_chat_stream_without_api_key_raises():
    import os

    for name in (
        "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
        "ROUTER_API_KEY",
        "NINEROUTER_API_KEY",
        "KILO_CODE_API_KEY",
        "OPENAI_API_KEY",
    ):
        os.environ.pop(name, None)
    http = _FakeStreamingHttp(lines=[])
    adapter = NineRouterAdapter(http_client=http)
    with pytest.raises(PermissionError, match="API key"):
        list(adapter.chat_stream(prompt="x"))


def test_chat_stream_handles_empty_stream():
    http = _FakeStreamingHttp(lines=[])
    adapter = NineRouterAdapter(api_key="k", http_client=http)
    chunks = list(adapter.chat_stream(prompt="x"))
    assert chunks == []


def test_chat_stream_handles_multiline_with_carriage_returns():
    """Real SSE often uses \\r\\n; the adapter should handle both."""
    http = _FakeStreamingHttp(
        lines=[
            'data: {"choices":[{"delta":{"content":"a"},"finish_reason":null}]}\r',
            "data: [DONE]\r",
        ]
    )
    adapter = NineRouterAdapter(api_key="k", http_client=http)
    chunks = list(adapter.chat_stream(prompt="x"))
    # Should still parse
    assert any(c["delta"] == "a" for c in chunks)
