"""9Router adapter — patched (v7).

v7 — F-29-RET1: `call()` returns upstream `GatewayResponse` (your local
     fix, now canonical). Defensive import — falls back to NineRouterResponse
     if the upstream model isn't importable, so the adapter still loads in
     a minimal-install context.

v6 history preserved:
  - chat_stream(messages, ...) → Iterator[{delta, finish_reason}] for SSE
  - 5 method aliases (chat / chat_completion / complete / call / invoke)
  - 5 env-var aliases for the API key
  - data: [DONE] sentinel handling
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping, Optional

# ── Defensive ABC import ──────────────────────────────────────────────────

try:
    from .base import ProviderAdapter as _BaseProviderAdapter  # type: ignore
    _HAS_UPSTREAM_BASE = True
except Exception:  # pragma: no cover
    _HAS_UPSTREAM_BASE = False
    class _BaseProviderAdapter:  # type: ignore[no-redef]
        provider_id: str = ""
        def is_configured(self) -> bool:
            return False


# ── F-29-RET1: defensive GatewayResponse import ─────────────────────────

try:
    from ..models.state import GatewayResponse as _GatewayResponse  # type: ignore
    _HAS_GATEWAY_RESPONSE = True
except Exception:  # pragma: no cover
    _HAS_GATEWAY_RESPONSE = False
    _GatewayResponse = None


PROVIDER_ID = "9router"
DEFAULT_BASE_URL = "http://localhost:20128/v1"
DEFAULT_MODEL = "kc/kilo-auto/free"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_STREAM_TIMEOUT_SECONDS = 300.0

_API_KEY_ENV_ALIASES = (
    "AI_PROVIDER_GATEWAY_9ROUTER_API_KEY",
    "ROUTER_API_KEY",
    "NINEROUTER_API_KEY",
    "KILO_CODE_API_KEY",
    "OPENAI_API_KEY",
)


@dataclass(frozen=True)
class NineRouterResponse:
    content: str
    model_actually_used: str
    finish_reason: str
    raw: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    @property
    def text(self) -> str:
        return self.content

    @property
    def message(self) -> str:
        return self.content

    @property
    def output(self) -> str:
        return self.content


def _resolve_api_key(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    for env_name in _API_KEY_ENV_ALIASES:
        v = os.environ.get(env_name)
        if v:
            return v
    return None


def _parse_quirky_body(body: str) -> dict[str, Any]:
    if not body:
        raise ValueError("empty response body")
    if "data:" in body:
        json_part = body.split("\ndata:", 1)[0]
        if json_part == body:
            json_part = body.split("data:", 1)[0]
        json_part = json_part.strip()
    else:
        json_part = body.strip()
    if not json_part:
        raise ValueError("no JSON content before sentinel")
    return json.loads(json_part)


def _extract_content(data: dict[str, Any]) -> tuple[str, str]:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("response had no 'choices' array")
    choice = choices[0]
    finish_reason = str(choice.get("finish_reason") or "")
    msg = choice.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content, finish_reason
    reasoning = msg.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning, finish_reason or "reasoning_only"
    legacy_text = choice.get("text")
    if isinstance(legacy_text, str) and legacy_text.strip():
        return legacy_text, finish_reason or "legacy_text"
    raise ValueError(
        "9router response had no usable content "
        "(message.content / message.reasoning / text all empty)"
    )


def _normalise_messages(messages_or_prompt, *, fallback_prompt=None):
    if messages_or_prompt is None:
        if fallback_prompt is None:
            raise ValueError("Provide messages= or prompt=")
        return [{"role": "user", "content": fallback_prompt}]
    if isinstance(messages_or_prompt, str):
        return [{"role": "user", "content": messages_or_prompt}]
    out = []
    for m in messages_or_prompt:
        if not isinstance(m, Mapping):
            raise TypeError(f"message must be a mapping, got {type(m).__name__}")
        out.append({"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")})
    if not out:
        raise ValueError("messages list was empty")
    return out


# ── HTTP transport ───────────────────────────────────────────────────────

class _HttpClient:
    def post_json(self, url, payload, *, api_key, timeout=DEFAULT_TIMEOUT_SECONDS, extra_headers=None):
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json, text/event-stream;q=0.9",
        }
        if extra_headers:
            headers.update(dict(extra_headers))
        req = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, raw, resp_headers
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            return e.code, raw, {k.lower(): v for k, v in (e.headers or {}).items()}
        except urllib.error.URLError as e:
            raise ConnectionError(f"9router unreachable at {url}: {e.reason}") from e

    def post_json_stream(self, url, payload, *, api_key, timeout=DEFAULT_STREAM_TIMEOUT_SECONDS):
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
        }
        req = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status >= 400:
                    err = resp.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"9router stream HTTP {resp.status}: {err[:500]}")
                buf = ""
                while True:
                    chunk = resp.read(1024)
                    if not chunk:
                        break
                    buf += chunk.decode("utf-8", errors="replace")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        yield line.rstrip("\r")
                if buf:
                    yield buf
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"9router stream HTTP {e.code}: {raw[:500]}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"9router unreachable at {url}: {e.reason}") from e


def _parse_sse_data_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    payload = line[len("data:"):].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _stream_event_to_chunk(event: dict[str, Any]) -> dict[str, Any]:
    choices = event.get("choices") or []
    if not choices:
        return {"delta": "", "finish_reason": ""}
    first = choices[0]
    delta_obj = first.get("delta") or {}
    delta_text = ""
    if isinstance(delta_obj, dict):
        delta_text = str(delta_obj.get("content") or "")
        if not delta_text:
            r = delta_obj.get("reasoning")
            if isinstance(r, str):
                delta_text = r
    finish = str(first.get("finish_reason") or "")
    return {"delta": delta_text, "finish_reason": finish}


# ── F-29-RET1: GatewayResponse construction ──────────────────────────────

def _to_gateway_response(
    content: str,
    *,
    model_used: str,
    finish_reason: str,
    input_tokens: int,
    output_tokens: int,
    provider_id: str = PROVIDER_ID,
    error: str = "",
) -> Any:
    """Construct an upstream GatewayResponse, defensively.

    Tries multiple plausible field names — different upstream versions use
    different schemas. Falls back to NineRouterResponse if GatewayResponse
    can't be constructed (so the adapter still works in minimal installs).

    F-29-RET1: this is the canonical form of your local fix.
    """
    if not _HAS_GATEWAY_RESPONSE or _GatewayResponse is None:
        return NineRouterResponse(
            content=content,
            model_actually_used=model_used,
            finish_reason=finish_reason,
            raw={},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    declared = set(getattr(_GatewayResponse, "model_fields", {}).keys())
    candidate_kwargs: dict[str, Any] = {
        "content": content,
        "response_text": content,
        "text": content,
        "output": content,
        "model_id_used": model_used,
        "model_actually_used": model_used,
        "model": model_used,
        "finish_reason": finish_reason,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "provider_id": provider_id,
        "error": error,
    }
    init_kwargs = {k: v for k, v in candidate_kwargs.items() if k in declared}

    # Ensure at least one content field is set (different versions may pick
    # a different canonical field; we set every plausible one we know of)
    try:
        return _GatewayResponse(**init_kwargs)
    except Exception:
        # Pydantic rejected something — fall back to NineRouterResponse
        return NineRouterResponse(
            content=content,
            model_actually_used=model_used,
            finish_reason=finish_reason,
            raw={},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ── Adapter ───────────────────────────────────────────────────────────────

class NineRouterAdapter(_BaseProviderAdapter):
    """OpenAI-compatible adapter for the local 9router."""

    provider_id: str = PROVIDER_ID
    name: str = "9Router (local OpenAI-compatible)"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        http_client: _HttpClient | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get(
            "AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL", DEFAULT_BASE_URL
        )).rstrip("/")
        self.model = model or os.environ.get(
            "AI_PROVIDER_GATEWAY_9ROUTER_MODEL", DEFAULT_MODEL
        )
        self._explicit_api_key = api_key
        self.timeout_seconds = float(
            timeout_seconds
            or os.environ.get("AI_PROVIDER_GATEWAY_9ROUTER_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        )
        self._http = http_client or _HttpClient()

    def is_configured(self) -> bool:
        return bool(_resolve_api_key(self._explicit_api_key))

    @property
    def model_id(self) -> str:
        return self.model

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    # ── chat (returns NineRouterResponse — adapter-test contract) ────────

    def chat(
        self,
        messages=None, *,
        prompt=None, model=None,
        max_tokens=512, temperature=0.0,
        extra_payload=None,
    ) -> NineRouterResponse:
        api_key = _resolve_api_key(self._explicit_api_key)
        if not api_key:
            raise PermissionError(
                "9router adapter has no API key. Set one of: "
                + ", ".join(_API_KEY_ENV_ALIASES)
            )

        norm_messages = _normalise_messages(messages, fallback_prompt=prompt)
        payload = {
            "model": model or self.model,
            "messages": norm_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra_payload:
            payload.update(dict(extra_payload))

        t0 = time.monotonic()
        status, raw_body, _headers = self._http.post_json(
            self.endpoint, payload, api_key=api_key, timeout=self.timeout_seconds,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if status >= 400:
            preview = (raw_body or "")[:500]
            raise RuntimeError(f"9router HTTP {status} at {self.endpoint}: {preview}")

        data = _parse_quirky_body(raw_body)
        content, finish_reason = _extract_content(data)
        usage = data.get("usage") or {}

        return NineRouterResponse(
            content=content,
            model_actually_used=str(data.get("model") or payload["model"]),
            finish_reason=finish_reason,
            raw=data,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=elapsed_ms,
        )

    # ── chat_stream (v6, unchanged) ─────────────────────────────────────

    def chat_stream(
        self,
        messages=None, *,
        prompt=None, model=None,
        max_tokens=512, temperature=0.0,
        extra_payload=None,
    ) -> Iterator[dict[str, Any]]:
        api_key = _resolve_api_key(self._explicit_api_key)
        if not api_key:
            raise PermissionError(
                "9router adapter has no API key. Set one of: "
                + ", ".join(_API_KEY_ENV_ALIASES)
            )

        norm_messages = _normalise_messages(messages, fallback_prompt=prompt)
        payload = {
            "model": model or self.model,
            "messages": norm_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if extra_payload:
            payload.update(dict(extra_payload))

        for line in self._http.post_json_stream(
            self.endpoint, payload, api_key=api_key,
            timeout=DEFAULT_STREAM_TIMEOUT_SECONDS,
        ):
            event = _parse_sse_data_line(line)
            if event is None:
                continue
            yield _stream_event_to_chunk(event)

    # ── F-29-RET1: call() → GatewayResponse (canonical) ─────────────────

    def call(
        self,
        messages=None, *,
        prompt=None, model=None,
        max_tokens=512, temperature=0.0,
        extra_payload=None,
    ) -> Any:
        """Like `chat()` but returns a `GatewayResponse` (canonical) so the
        upstream `provider_call_node` can thread it through
        `response_validation_node` without a shape adapter.

        On RuntimeError (HTTP 4xx/5xx), returns a GatewayResponse with the
        error field populated instead of re-raising — preserves your local
        graceful-failure behaviour.
        """
        try:
            r = self.chat(
                messages=messages, prompt=prompt, model=model,
                max_tokens=max_tokens, temperature=temperature,
                extra_payload=extra_payload,
            )
            return _to_gateway_response(
                content=r.content,
                model_used=r.model_actually_used,
                finish_reason=r.finish_reason,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                provider_id=PROVIDER_ID,
            )
        except PermissionError as e:
            return _to_gateway_response(
                content="", model_used=model or self.model,
                finish_reason="auth_failed",
                input_tokens=0, output_tokens=0,
                error=f"PermissionError: {e}",
            )
        except (RuntimeError, ConnectionError) as e:
            return _to_gateway_response(
                content="", model_used=model or self.model,
                finish_reason="error",
                input_tokens=0, output_tokens=0,
                error=str(e),
            )

    # ── Aliases for other graph dispatch variants ─────────────────────────

    def chat_completion(self, *a, **kw):
        return self.chat(*a, **kw)

    def complete(self, *a, **kw):
        return self.chat(*a, **kw)

    def invoke(self, *a, **kw):
        return self.chat(*a, **kw)

    def supports(self, capability: str) -> bool:
        return capability in ("chat", "code")


__all__ = [
    "PROVIDER_ID", "DEFAULT_BASE_URL", "DEFAULT_MODEL",
    "NineRouterAdapter", "NineRouterResponse",
    "_parse_quirky_body", "_extract_content", "_resolve_api_key",
    "_parse_sse_data_line", "_stream_event_to_chunk",
    "_to_gateway_response",
]
