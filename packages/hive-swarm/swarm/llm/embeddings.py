"""Pluggable embedding providers (v7: OpenAIEmbeddingAdapter).

v6 shipped:
  - NullEmbedder, HashEmbedder, GatewayEmbedder
  - cosine_similarity helper
  - process-wide default embedder registry

v7 adds:
  - OpenAIEmbeddingAdapter — real semantic embeddings via OpenAI's
    /embeddings endpoint. Pure stdlib (urllib.request, no openai dep).
    Looks up API key from a tuple of env-var aliases (OPENAI_API_KEY first).
    On any failure (no key, network error, malformed response): returns []
    so the caller falls back to keyword/HashEmbedder.

  - default_embedder_from_env(): convenience that returns
    OpenAIEmbeddingAdapter() if any OpenAI-style key is present,
    else HashEmbedder() — so a process can call this once at startup and
    get the best available embedder without manual configuration.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional, Protocol


# ── Protocol ─────────────────────────────────────────────────────────────


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


# ── Null ────────────────────────────────────────────────────────────────


class NullEmbedder:
    def embed(self, text: str) -> list[float]:
        return []

    def __repr__(self):  # pragma: no cover
        return "NullEmbedder()"


# ── HashEmbedder (v6, unchanged) ─────────────────────────────────────────


class HashEmbedder:
    DIMS = 32

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return []
        tokens = text.lower().split()
        if not tokens:
            return []
        accum = [0.0] * self.DIMS
        for tok in tokens:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            for i in range(self.DIMS):
                accum[i] += (h[i] - 128) / 128.0
        norm = math.sqrt(sum(x * x for x in accum))
        if norm == 0.0:
            return [0.0] * self.DIMS
        return [x / norm for x in accum]

    def __repr__(self):  # pragma: no cover
        return f"HashEmbedder(dims={self.DIMS})"


# ── GatewayEmbedder (v6, unchanged) ──────────────────────────────────────


class GatewayEmbedder:
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
        for name in ("embed", "embed_text", "embeddings", "embedding"):
            method = getattr(adapter, name, None)
            if not callable(method):
                continue
            try:
                if self.model_id:
                    out = method(text, model=self.model_id)
                else:
                    out = method(text)
                return list(out) if out else []
            except Exception:
                return []
        return []

    def __repr__(self):  # pragma: no cover
        return f"GatewayEmbedder(provider_id={self.provider_id!r})"


# ── v7: OpenAIEmbeddingAdapter ───────────────────────────────────────────

_OPENAI_KEY_ENV_ALIASES = (
    "OPENAI_API_KEY",
    "OPENAI_EMBEDDINGS_API_KEY",
    "AI_PROVIDER_OPENAI_API_KEY",
)
_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
_DEFAULT_OPENAI_TIMEOUT = 30.0
_ALLOWED_URL_SCHEMES = {"http", "https"}


def _validate_http_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.netloc:
        raise ValueError(f"URL must be absolute HTTP(S): {url!r}")
    return url


class _EmbeddingsHttpClient:
    """Stdlib HTTP client (injectable for tests)."""

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout: float = _DEFAULT_OPENAI_TIMEOUT,
    ) -> tuple[int, str]:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req = urllib.request.Request(
            url=_validate_http_url(url), data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                raw = resp.read().decode("utf-8", errors="replace")
                return resp.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            return e.code, raw
        except urllib.error.URLError as e:
            raise ConnectionError(f"OpenAI embeddings unreachable at {url}: {e.reason}") from e


class OpenAIEmbeddingAdapter:
    """Real semantic embeddings via OpenAI /embeddings.

    Designed to be drop-in for `set_default_embedder(OpenAIEmbeddingAdapter())`.

    Failure modes — all return `[]` so the caller (SwarmState._check_drift_embedding)
    falls back to keyword detection:
      - no API key in any of the env-var aliases
      - HTTP 4xx / 5xx
      - network error
      - malformed JSON response
      - missing 'data[0].embedding' field

    Args:
      base_url: override the default api.openai.com endpoint
      model: embedding model id (default: text-embedding-3-small)
      api_key: explicit key (otherwise read from env)
      timeout_seconds: HTTP timeout
      http_client: injected client for tests
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str = _DEFAULT_OPENAI_MODEL,
        api_key: str | None = None,
        timeout_seconds: float = _DEFAULT_OPENAI_TIMEOUT,
        http_client: _EmbeddingsHttpClient | None = None,
    ) -> None:
        self.base_url = (base_url or _DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self.model = model
        self._explicit_api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._http = http_client or _EmbeddingsHttpClient()

    def _resolve_key(self) -> str | None:
        if self._explicit_api_key:
            return self._explicit_api_key
        for env_name in _OPENAI_KEY_ENV_ALIASES:
            v = os.environ.get(env_name)
            if v:
                return v
        return None

    def is_configured(self) -> bool:
        return bool(self._resolve_key())

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/embeddings"

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return []
        api_key = self._resolve_key()
        if not api_key:
            return []

        payload = {"model": self.model, "input": text}
        try:
            status, raw = self._http.post_json(
                self.endpoint,
                payload,
                api_key=api_key,
                timeout=self.timeout_seconds,
            )
        except ConnectionError:
            return []
        except Exception:
            return []

        if status >= 400:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        # OpenAI shape: {"data": [{"embedding": [...]}], ...}
        try:
            entries = data.get("data") or []
            if not entries:
                return []
            first = entries[0]
            if not isinstance(first, dict):
                return []
            embedding = first.get("embedding")
            if not isinstance(embedding, list):
                return []
            # Coerce to float; drop entry if any element fails
            try:
                return [float(x) for x in embedding]
            except (TypeError, ValueError):
                return []
        except Exception:
            return []

    def __repr__(self):  # pragma: no cover
        return f"OpenAIEmbeddingAdapter(model={self.model!r})"


class SentenceTransformerEmbedder:
    """Local sentence-transformers embedder.

    The optional dependency and model are loaded lazily. Missing packages or
    model load failures return ``[]`` so callers can fall back safely.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", *, model: Any | None = None) -> None:
        self.model_name = model_name
        self._model = model
        self._load_attempted = model is not None

    def _resolve_model(self) -> Any | None:
        if self._load_attempted:
            return self._model
        self._load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except Exception:
            self._model = None
            return None
        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception:
            self._model = None
        return self._model

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return []
        model = self._resolve_model()
        if model is None:
            return []
        try:
            vector = model.encode(text)
            if hasattr(vector, "tolist"):
                vector = vector.tolist()
            return [float(value) for value in vector]
        except Exception:
            return []

    def __repr__(self):  # pragma: no cover
        return f"SentenceTransformerEmbedder(model_name={self.model_name!r})"


# ── Cosine similarity (no numpy) ─────────────────────────────────────────


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Default embedder registry + auto-detect helper ───────────────────────

_DEFAULT_EMBEDDER: EmbeddingProvider = NullEmbedder()


def set_default_embedder(embedder: EmbeddingProvider) -> None:
    global _DEFAULT_EMBEDDER
    _DEFAULT_EMBEDDER = embedder


def get_default_embedder() -> EmbeddingProvider:
    return _DEFAULT_EMBEDDER


def default_embedder_from_env() -> EmbeddingProvider:
    """v7: pick the best available embedder without manual config.

    Priority:
      1. OpenAIEmbeddingAdapter() if any OPENAI_* env key present
      2. HashEmbedder() otherwise (deterministic, no network)

    Useful for app startup:
        from swarm.llm.embeddings import default_embedder_from_env, set_default_embedder
        set_default_embedder(default_embedder_from_env())
    """
    for env_name in _OPENAI_KEY_ENV_ALIASES:
        if os.environ.get(env_name):
            return OpenAIEmbeddingAdapter()
    return HashEmbedder()


__all__ = [
    "EmbeddingProvider",
    "NullEmbedder",
    "HashEmbedder",
    "GatewayEmbedder",
    "OpenAIEmbeddingAdapter",
    "SentenceTransformerEmbedder",
    "cosine_similarity",
    "set_default_embedder",
    "get_default_embedder",
    "default_embedder_from_env",
]
