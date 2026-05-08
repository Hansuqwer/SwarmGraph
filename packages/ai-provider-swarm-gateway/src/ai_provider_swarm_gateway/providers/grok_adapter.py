"""xAI Grok adapter using the OpenAI-compatible chat API."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..models.state import GatewayResponse
from .base import ProviderAdapter

PROVIDER_ID = "grok"
DEFAULT_BASE_URL = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-2-latest"
_KEY_ENV_ALIASES = ("XAI_API_KEY", "AI_PROVIDER_GROK_API_KEY")


def _validate_https_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"URL must be absolute HTTPS: {url!r}")
    return url


class _GrokHttpClient:
    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout: float,
    ) -> tuple[int, str]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=_validate_https_url(url),
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return exc.code, raw
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Grok unreachable at {url}: {exc.reason}") from exc


class GrokAdapter(ProviderAdapter):
    provider_id = PROVIDER_ID
    default_model = DEFAULT_MODEL

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        http_client: _GrokHttpClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._http = http_client or _GrokHttpClient()

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _resolve_key(self) -> str | None:
        if self._api_key:
            return self._api_key
        for env_name in _KEY_ENV_ALIASES:
            value = os.environ.get(env_name)
            if value:
                return value
        return None

    def is_configured(self) -> bool:
        return bool(self._resolve_key())

    def call(self, prompt: str, model: str | None = None, **kwargs: Any) -> GatewayResponse:
        api_key = self._resolve_key()
        target_model = model or self.default_model
        if not api_key:
            return self._not_configured_response()

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0.0),
            "stream": False,
        }
        if kwargs.get("x_search") is True:
            payload["include_x_search"] = True

        try:
            status, raw = self._http.post_json(
                self.endpoint,
                payload,
                api_key=api_key,
                timeout=self.timeout_seconds,
            )
            if status >= 400:
                return self._error_response(f"Grok HTTP {status}: {raw[:500]}")
            data = json.loads(raw)
            choices = data.get("choices") or []
            if not choices:
                return self._error_response("Grok response had no choices")
            choice = choices[0]
            message = choice.get("message") or {}
            usage = data.get("usage") or {}
            return GatewayResponse(
                provider_id=self.provider_id,
                model_id=str(data.get("model") or target_model),
                content=message.get("content"),
                raw=data,
                tokens_used=int(usage.get("total_tokens") or 0),
            )
        except Exception as exc:
            return self._error_response(str(exc))


__all__ = ["GrokAdapter"]
