import json

from ai_provider_swarm_gateway.graph.nodes import _get_adapter
from ai_provider_swarm_gateway.providers.grok_adapter import GrokAdapter, _validate_https_url


class _FakeHttp:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body or {
            "model": "grok-test",
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 7},
        }
        self.payload = None

    def post_json(self, url, payload, *, api_key, timeout):
        assert api_key == "secret"
        assert url == "https://api.x.ai/v1/chat/completions"
        self.payload = payload
        return self.status, json.dumps(self.body) if isinstance(self.body, dict) else self.body


def test_grok_adapter_not_configured():
    response = GrokAdapter(api_key=None).call("hello")

    assert response.error
    assert response.content is None


def test_grok_adapter_success():
    http = _FakeHttp()
    adapter = GrokAdapter(api_key="secret", http_client=http)

    response = adapter.call("hello", x_search=True)

    assert response.error is None
    assert response.content == "hello"
    assert response.model_id == "grok-test"
    assert response.tokens_used == 7
    assert http.payload["include_x_search"] is True


def test_grok_adapter_http_error():
    adapter = GrokAdapter(api_key="secret", http_client=_FakeHttp(status=429, body="rate limit"))

    response = adapter.call("hello")

    assert "Grok HTTP 429" in (response.error or "")


def test_grok_url_requires_https():
    try:
        _validate_https_url("http://example.com")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_get_adapter_returns_grok_adapter():
    assert isinstance(_get_adapter("grok"), GrokAdapter)
