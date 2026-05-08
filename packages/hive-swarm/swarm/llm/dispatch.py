"""WorkerLLMDispatcher — patched (v7).

v7 — F-17-ENV1: HIVE_SWARM_COST_TRACKING env var support, symmetric with
     HIVE_SWARM_LLM_STREAM. Values "0", "false", "no", "off" disable
     cost tracking even if SwarmConfig says otherwise.

History (v4–v6 preserved):
  - StreamChunk + dispatch_stream
  - WorkerLLMResponse + dispatch_full
  - per-role provider + model overrides
  - SONA-retrieved patterns reach user prompt
  - cost lookup via swarm_shared.pricing
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional, Protocol

from swarm_shared.pricing import DEFAULT_PRICING_TABLE, PricingTable

from .prompts import get_system_prompt


class WorkerLLMError(RuntimeError):
    pass


class StreamingHITLInterrupt(RuntimeError):
    """Raised by GatewayDispatcher.dispatch_stream when a streaming guard fires.

    Attributes:
      reason: short string identifying the trigger ('pattern_match' or 'max_chars_exceeded')
      partial_text: the accumulated streamed output up to the trigger
      matched_pattern: regex source if reason == 'pattern_match'; empty otherwise
      char_count: len(partial_text)
    """

    def __init__(
        self,
        reason: str,
        partial_text: str,
        *,
        matched_pattern: str = "",
    ) -> None:
        super().__init__(f"streaming HITL: {reason}")
        self.reason = reason
        self.partial_text = partial_text
        self.matched_pattern = matched_pattern
        self.char_count = len(partial_text)


@dataclass(frozen=True)
class StreamChunk:
    delta: str
    text: str
    index: int
    done: bool = False
    finish_reason: str = ""


@dataclass(frozen=True)
class WorkerLLMResponse:
    text: str
    backend: str
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model_id_used: str = ""
    finish_reason: str = ""
    provider_id: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ── Defaults + settings resolution ───────────────────────────────────────

DEFAULT_SETTINGS: dict[str, Any] = {
    "backend": "stub",
    "default_provider": "9router",
    "default_model": "",
    "max_tokens": 512,
    "temperature": 0.0,
    "timeout_seconds": 60.0,
    "role_provider_overrides": {},
    "role_model_overrides": {},
    "include_retrieved_patterns": True,
    "include_objective": True,
    "stream_enabled": False,
    "cost_tracking_enabled": True,
}

_ENV_BACKEND = "HIVE_SWARM_LLM_BACKEND"
_ENV_PROVIDER = "HIVE_SWARM_LLM_PROVIDER"
_ENV_MODEL = "HIVE_SWARM_LLM_MODEL"
_ENV_MAX_TOKENS = "HIVE_SWARM_LLM_MAX_TOKENS"
_ENV_TEMPERATURE = "HIVE_SWARM_LLM_TEMPERATURE"
_ENV_STREAM = "HIVE_SWARM_LLM_STREAM"
_ENV_COST = "HIVE_SWARM_COST_TRACKING"   # v7 NEW (F-17-ENV1)


_FALSY_STRINGS = ("0", "false", "no", "off", "")
_TRUTHY_STRINGS = ("1", "true", "yes", "on")


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    s = v.strip().lower()
    if s in _TRUTHY_STRINGS:
        return True
    if s in _FALSY_STRINGS:
        return False
    return default


def resolve_llm_settings(
    task_context: dict[str, Any] | None,
    role: str | None = None,
) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)

    if task_context:
        shared = task_context.get("shared_context") or {}
        if isinstance(shared, dict):
            queen_settings = shared.get("llm_settings") or {}
            if isinstance(queen_settings, dict):
                for k, v in queen_settings.items():
                    if v is not None:
                        settings[k] = v

    if os.environ.get(_ENV_BACKEND):
        settings["backend"] = os.environ[_ENV_BACKEND].strip().lower()
    if os.environ.get(_ENV_PROVIDER):
        settings["default_provider"] = os.environ[_ENV_PROVIDER].strip()
    if os.environ.get(_ENV_MODEL):
        settings["default_model"] = os.environ[_ENV_MODEL].strip()
    if os.environ.get(_ENV_MAX_TOKENS):
        try:
            settings["max_tokens"] = int(os.environ[_ENV_MAX_TOKENS])
        except ValueError:
            pass
    if os.environ.get(_ENV_TEMPERATURE):
        try:
            settings["temperature"] = float(os.environ[_ENV_TEMPERATURE])
        except ValueError:
            pass
    if os.environ.get(_ENV_STREAM) is not None:
        settings["stream_enabled"] = _env_bool(_ENV_STREAM, settings["stream_enabled"])
    # v7 — F-17-ENV1
    if os.environ.get(_ENV_COST) is not None:
        settings["cost_tracking_enabled"] = _env_bool(
            _ENV_COST, settings["cost_tracking_enabled"]
        )

    p_overrides = settings.get("role_provider_overrides") or {}
    if isinstance(p_overrides, dict) and role and role in p_overrides:
        settings["effective_provider"] = p_overrides[role]
    else:
        settings["effective_provider"] = settings["default_provider"]

    m_overrides = settings.get("role_model_overrides") or {}
    if isinstance(m_overrides, dict) and role and role in m_overrides:
        settings["effective_model"] = m_overrides[role]
    else:
        settings["effective_model"] = settings.get("default_model") or ""

    return settings


# ── Prompt building (unchanged from v6) ──────────────────────────────────

def _build_user_prompt(
    task_description, task_context, *,
    include_retrieved_patterns=True, include_objective=True,
    max_pattern_chars=300, max_patterns=5,
):
    parts = [task_description.strip()]
    shared = (task_context or {}).get("shared_context") or {}
    if not isinstance(shared, dict):
        shared = {}

    if include_retrieved_patterns:
        patterns = shared.get("retrieved_patterns") or []
        if isinstance(patterns, list) and patterns:
            usable = []
            for p in patterns[:max_patterns]:
                if not isinstance(p, dict):
                    continue
                value = str(p.get("value") or "")[:max_pattern_chars]
                if not value.strip():
                    continue
                score = p.get("score")
                tag = f"[score={score:.2f}]" if isinstance(score, (int, float)) else ""
                usable.append(f"- {tag} {value}")
            if usable:
                parts.append("\nRelevant patterns from prior swarm runs (SONA memory):")
                parts.extend(usable)

    if include_objective:
        objective = str(shared.get("objective") or "").strip()
        if objective and objective.lower() not in task_description.lower():
            parts.append(f"\nOverall swarm objective: {objective}")

    return "\n".join(parts)


# ── Response extraction helpers (unchanged from v6) ──────────────────────

_TEXT_ATTR_CANDIDATES = (
    "content", "text", "response_text", "output", "message",
    "final_response", "validated_response",
)
_DICT_KEY_CANDIDATES = (
    "content", "text", "response_text", "output", "final_response",
    "validated_response",
)
_USAGE_ATTR_CANDIDATES = ("usage", "token_usage")
_INPUT_TOKEN_KEYS = ("input_tokens", "prompt_tokens")
_OUTPUT_TOKEN_KEYS = ("output_tokens", "completion_tokens", "generated_tokens")


def _extract_text(resp):
    if resp is None:
        raise WorkerLLMError("adapter returned None")
    if isinstance(resp, str):
        if not resp.strip():
            raise WorkerLLMError("adapter returned empty string")
        return resp
    for attr in _TEXT_ATTR_CANDIDATES:
        if not hasattr(resp, attr):
            continue
        v = getattr(resp, attr)
        if isinstance(v, str) and v.strip():
            return v
        if v is not None:
            if hasattr(v, "content") and isinstance(v.content, str) and v.content.strip():
                return v.content
            if isinstance(v, dict):
                inner = v.get("content")
                if isinstance(inner, str) and inner.strip():
                    return inner
    if isinstance(resp, dict):
        for k in _DICT_KEY_CANDIDATES:
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return v
        choices = resp.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    c = msg.get("content")
                    if isinstance(c, str) and c.strip():
                        return c
                    r = msg.get("reasoning")
                    if isinstance(r, str) and r.strip():
                        return r
                t = first.get("text")
                if isinstance(t, str) and t.strip():
                    return t
    s = str(resp)
    if s.startswith("<") and s.endswith(">"):
        raise WorkerLLMError(
            f"could not extract text from response of type {type(resp).__name__}"
        )
    return s


def _read_int_field(obj, names):
    for name in names:
        v = None
        if isinstance(obj, dict):
            v = obj.get(name)
        elif hasattr(obj, name):
            v = getattr(obj, name)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return 0


def _extract_usage(resp):
    if resp is None or isinstance(resp, str):
        return 0, 0
    for attr_in in _INPUT_TOKEN_KEYS:
        if hasattr(resp, attr_in):
            try:
                in_t = int(getattr(resp, attr_in) or 0)
                out_t = 0
                for attr_out in _OUTPUT_TOKEN_KEYS:
                    if hasattr(resp, attr_out):
                        out_t = int(getattr(resp, attr_out) or 0)
                        break
                if in_t or out_t:
                    return in_t, out_t
            except (TypeError, ValueError):
                pass
    for attr in _USAGE_ATTR_CANDIDATES:
        if hasattr(resp, attr):
            usage = getattr(resp, attr)
            if usage is None:
                continue
            in_t = _read_int_field(usage, _INPUT_TOKEN_KEYS)
            out_t = _read_int_field(usage, _OUTPUT_TOKEN_KEYS)
            if in_t or out_t:
                return in_t, out_t
    if isinstance(resp, dict):
        for attr in _USAGE_ATTR_CANDIDATES:
            usage = resp.get(attr)
            if isinstance(usage, dict):
                in_t = _read_int_field(usage, _INPUT_TOKEN_KEYS)
                out_t = _read_int_field(usage, _OUTPUT_TOKEN_KEYS)
                if in_t or out_t:
                    return in_t, out_t
        in_t = _read_int_field(resp, _INPUT_TOKEN_KEYS)
        out_t = _read_int_field(resp, _OUTPUT_TOKEN_KEYS)
        if in_t or out_t:
            return in_t, out_t
    return 0, 0


def _extract_model_id(resp, fallback=""):
    for attr in ("model_actually_used", "model_id_used", "model", "model_id"):
        if hasattr(resp, attr):
            v = getattr(resp, attr)
            if isinstance(v, str) and v:
                return v
    if isinstance(resp, dict):
        for k in ("model_actually_used", "model_id_used", "model", "model_id"):
            v = resp.get(k)
            if isinstance(v, str) and v:
                return v
    return fallback


def _extract_finish_reason(resp):
    for attr in ("finish_reason", "stop_reason"):
        if hasattr(resp, attr):
            v = getattr(resp, attr)
            if isinstance(v, str) and v:
                return v
    if isinstance(resp, dict):
        for k in ("finish_reason", "stop_reason"):
            v = resp.get(k)
            if isinstance(v, str) and v:
                return v
        choices = resp.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            v = choices[0].get("finish_reason")
            if isinstance(v, str):
                return v
    return ""


# ── Dispatcher protocol (unchanged from v6) ──────────────────────────────

class WorkerLLMDispatcher(Protocol):
    def dispatch(self, role, task_description, context=None) -> str: ...
    def dispatch_full(self, role, task_description, context=None) -> WorkerLLMResponse: ...
    def dispatch_stream(self, role, task_description, context=None) -> Iterator[StreamChunk]: ...


# ── Stub dispatcher (unchanged from v6) ──────────────────────────────────

_STUB_TEMPLATES = {
    "researcher": "[RESEARCHER] Analysis of: {desc}",
    "architect":  "[ARCHITECT] Design for: {desc}",
    "coder":      "[CODER] Implementation for: {desc}",
    "tester":     "[TESTER] Test suite for: {desc}",
    "reviewer":   "[REVIEWER] Review for: {desc}",
    "security":   "[SECURITY] Security audit for: {desc}",
    "optimizer":  "[OPTIMIZER] Optimization analysis for: {desc}",
    "coordinator": "[COORDINATOR] Coordination plan for: {desc}",
    "queen":      "[COORDINATOR] Coordination plan for: {desc}",
    "documenter": "[AGENT] Output for: {desc}",
}
_STUB_DEFAULT = "[AGENT] Output for: {desc}"


class StubDispatcher:
    def __init__(self, *, max_desc_chars=200):
        self.max_desc_chars = max_desc_chars

    def dispatch(self, role, task_description, context=None):
        return self.dispatch_full(role, task_description, context).text

    def dispatch_full(self, role, task_description, context=None):
        template = _STUB_TEMPLATES.get(role, _STUB_DEFAULT)
        text = template.format(desc=task_description[: self.max_desc_chars])
        return WorkerLLMResponse(
            text=text, backend="stub",
            input_tokens=0, output_tokens=0,
            model_id_used="stub:deterministic",
            finish_reason="stop", provider_id="stub",
        )

    def dispatch_stream(self, role, task_description, context=None):
        full = self.dispatch_full(role, task_description, context)
        yield StreamChunk(delta=full.text, text=full.text, index=0, done=True, finish_reason="stop")


# ── Gateway dispatcher (unchanged from v6) ───────────────────────────────

_AdapterFactory = Callable[[str], Any]


def _default_adapter_factory(provider_id):
    try:
        from ai_provider_swarm_gateway.graph.nodes import _get_adapter  # type: ignore
    except ImportError as e:
        raise WorkerLLMError(
            "ai-provider-swarm-gateway is not installed; "
            "install it to use llm_backend='gateway'."
        ) from e
    return _get_adapter(provider_id)


import re as _re_v8


class _StreamingGuard:
    """Per-chunk guard for streaming dispatch.

    Cheap-first check order:
      1. Length cap (single int comparison)
      2. Pattern check (only every N chunks; throttled)

    Raises StreamingHITLInterrupt on first trigger. Returns silently otherwise.
    """

    def __init__(
        self,
        *,
        guard_patterns: list[str] | None = None,
        max_output_chars: int = 16384,
        check_every_n_chunks: int = 4,
    ) -> None:
        self.compiled_patterns = [
            _re_v8.compile(p) for p in (guard_patterns or [])
        ]
        self.max_output_chars = int(max_output_chars)
        self.check_every_n_chunks = max(1, int(check_every_n_chunks))
        self._chunks_since_check = 0

    def check(self, accumulated_text: str, chunk_index: int) -> None:
        """Inspect the accumulated text. Raise if a guard fires."""
        # Length cap is cheap — check every chunk
        if len(accumulated_text) > self.max_output_chars:
            raise StreamingHITLInterrupt(
                "max_chars_exceeded",
                accumulated_text,
            )

        # Throttle pattern checks
        self._chunks_since_check += 1
        if self._chunks_since_check < self.check_every_n_chunks:
            return
        self._chunks_since_check = 0

        for pat in self.compiled_patterns:
            m = pat.search(accumulated_text)
            if m is not None:
                raise StreamingHITLInterrupt(
                    "pattern_match",
                    accumulated_text,
                    matched_pattern=pat.pattern,
                )


class GatewayDispatcher:
    _METHOD_CANDIDATES = ("chat", "chat_completion", "complete", "call", "invoke")

    def __init__(self, *, default_provider="9router", default_model="",
                 max_tokens=512, temperature=0.0, timeout_seconds=60.0,
                 include_retrieved_patterns=True, include_objective=True,
                 role_provider_overrides=None, role_model_overrides=None,
                 adapter_factory=None):
        self.default_provider = default_provider
        self.default_model = default_model
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.timeout_seconds = float(timeout_seconds)
        self.include_retrieved_patterns = bool(include_retrieved_patterns)
        self.include_objective = bool(include_objective)
        self.role_provider_overrides = dict(role_provider_overrides or {})
        self.role_model_overrides = dict(role_model_overrides or {})
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._adapter_cache: dict[str, Any] = {}

    def _provider_for_role(self, role):
        return self.role_provider_overrides.get(role, self.default_provider)

    def _model_for_role(self, role):
        return self.role_model_overrides.get(role, self.default_model)

    def _ensure_adapter(self, provider_id):
        if provider_id not in self._adapter_cache:
            self._adapter_cache[provider_id] = self._adapter_factory(provider_id)
        return self._adapter_cache[provider_id]

    def _call_adapter(self, adapter, *, system_prompt, user_prompt, model_id=""):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs_with_model = {"max_tokens": self.max_tokens, "temperature": self.temperature}
        if model_id:
            kwargs_with_model["model"] = model_id

        last_err = None
        for name in self._METHOD_CANDIDATES:
            method = getattr(adapter, name, None)
            if not callable(method):
                continue
            try:
                return method(messages=messages, **kwargs_with_model)
            except TypeError as e:
                last_err = e
                if "model" in kwargs_with_model:
                    try:
                        kwargs_no_model = {k: v for k, v in kwargs_with_model.items() if k != "model"}
                        return method(messages=messages, **kwargs_no_model)
                    except TypeError as e2:
                        last_err = e2
                try:
                    return method(prompt=user_prompt, **{k: v for k, v in kwargs_with_model.items() if k != "model"})
                except TypeError as e3:
                    last_err = e3
                try:
                    return method(user_prompt)
                except Exception as e4:
                    last_err = e4
                    continue
            except Exception as e:
                raise WorkerLLMError(
                    f"adapter {type(adapter).__name__}.{name}() raised: {e}"
                ) from e

        raise WorkerLLMError(
            f"no callable LLM method on adapter {type(adapter).__name__} "
            f"(tried: {', '.join(self._METHOD_CANDIDATES)}); last error: {last_err}"
        )

    def dispatch(self, role, task_description, context=None):
        return self.dispatch_full(role, task_description, context).text

    def dispatch_full(self, role, task_description, context=None):
        provider_id = self._provider_for_role(role)
        model_id = self._model_for_role(role)

        try:
            adapter = self._ensure_adapter(provider_id)
        except WorkerLLMError:
            raise
        except Exception as e:
            raise WorkerLLMError(f"could not load adapter {provider_id!r}: {e}") from e

        if not getattr(adapter, "is_configured", lambda: True)():
            raise WorkerLLMError(
                f"adapter {provider_id!r} is not configured "
                f"(typically missing API key env var)"
            )

        system_prompt = get_system_prompt(role)
        user_prompt = _build_user_prompt(
            task_description, context,
            include_retrieved_patterns=self.include_retrieved_patterns,
            include_objective=self.include_objective,
        )

        t0 = time.monotonic()
        resp = self._call_adapter(
            adapter, system_prompt=system_prompt,
            user_prompt=user_prompt, model_id=model_id,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        text = _extract_text(resp)
        in_tok, out_tok = _extract_usage(resp)
        actual_model = _extract_model_id(resp, fallback=model_id or "unknown")
        finish_reason = _extract_finish_reason(resp)

        return WorkerLLMResponse(
            text=text, backend="gateway", latency_ms=latency_ms,
            input_tokens=in_tok, output_tokens=out_tok,
            model_id_used=actual_model, finish_reason=finish_reason,
            provider_id=provider_id,
        )

    def dispatch_stream(self, role, task_description, context=None):
        """v8: per-chunk guards via _StreamingGuard."""
        provider_id = self._provider_for_role(role)
        model_id = self._model_for_role(role)

        try:
            adapter = self._ensure_adapter(provider_id)
        except WorkerLLMError:
            raise
        except Exception as e:
            raise WorkerLLMError(f"could not load adapter {provider_id!r}: {e}") from e

        if not getattr(adapter, "is_configured", lambda: True)():
            raise WorkerLLMError(f"adapter {provider_id!r} is not configured")

        # v8: build the streaming guard from queen-forwarded settings
        guard_patterns: list[str] = []
        max_output_chars = 16384
        check_every_n_chunks = 4
        if context:
            shared = context.get("shared_context") or {}
            ls = shared.get("llm_settings") or {}
            guard_patterns = list(ls.get("streaming_guard_patterns") or [])
            max_output_chars = int(ls.get("streaming_max_output_chars") or 16384)
            check_every_n_chunks = int(ls.get("streaming_guard_check_every_n_chunks") or 4)
        guard = _StreamingGuard(
            guard_patterns=guard_patterns,
            max_output_chars=max_output_chars,
            check_every_n_chunks=check_every_n_chunks,
        )

        chat_stream = getattr(adapter, "chat_stream", None)
        if not callable(chat_stream):
            full = self.dispatch_full(role, task_description, context)
            yield StreamChunk(
                delta=full.text, text=full.text, index=0,
                done=True, finish_reason=full.finish_reason or "stop",
            )
            return

        system_prompt = get_system_prompt(role)
        user_prompt = _build_user_prompt(
            task_description, context,
            include_retrieved_patterns=self.include_retrieved_patterns,
            include_objective=self.include_objective,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs = {"max_tokens": self.max_tokens, "temperature": self.temperature}
        if model_id:
            kwargs["model"] = model_id

        try:
            stream = chat_stream(messages=messages, **kwargs)
        except TypeError:
            try:
                stream = chat_stream(messages=messages, **{k: v for k, v in kwargs.items() if k != "model"})
            except Exception as e:
                raise WorkerLLMError(f"chat_stream call failed: {e}") from e
        except Exception as e:
            raise WorkerLLMError(f"chat_stream call failed: {e}") from e

        accumulated = ""
        index = 0
        last_finish = ""
        try:
            for raw in stream:
                delta, finish = _normalise_stream_chunk(raw)
                if delta:
                    accumulated += delta
                last_finish = finish or last_finish

                # v8: guard check (raises StreamingHITLInterrupt on trigger)
                guard.check(accumulated, index)

                yield StreamChunk(
                    delta=delta, text=accumulated, index=index,
                    done=False, finish_reason=last_finish,
                )
                index += 1
        except StreamingHITLInterrupt:
            # Re-raise; worker_node catches it
            raise
        except Exception as e:
            raise WorkerLLMError(f"chat_stream iteration raised: {e}") from e

        yield StreamChunk(
            delta="", text=accumulated, index=index,
            done=True, finish_reason=last_finish or "stop",
        )


def _normalise_stream_chunk(raw):
    if raw is None:
        return "", ""
    if isinstance(raw, str):
        return raw, ""
    if hasattr(raw, "delta") and isinstance(raw.delta, str):
        return raw.delta, str(getattr(raw, "finish_reason", "") or "")
    if isinstance(raw, dict):
        if "delta" in raw and isinstance(raw["delta"], str):
            return raw["delta"], str(raw.get("finish_reason") or "")
        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                d = first.get("delta") or {}
                if isinstance(d, dict):
                    content = d.get("content") or ""
                    finish = first.get("finish_reason") or ""
                    return str(content), str(finish or "")
                t = first.get("text")
                if isinstance(t, str):
                    return t, str(first.get("finish_reason") or "")
    return "", ""


def estimate_call_cost(model_id, input_tokens, output_tokens, *, table=None):
    return (table or DEFAULT_PRICING_TABLE).estimate_cost(
        model_id, input_tokens, output_tokens
    )


def build_dispatcher(settings):
    backend = (settings.get("backend") or "stub").lower()

    if backend in ("stub", "off", "none", "false", "0"):
        return StubDispatcher()

    if backend == "gateway":
        provider = (
            settings.get("effective_provider")
            or settings.get("default_provider")
            or "9router"
        )
        model = settings.get("effective_model") or settings.get("default_model") or ""
        return GatewayDispatcher(
            default_provider=provider,
            default_model=model,
            max_tokens=int(settings.get("max_tokens", 512)),
            temperature=float(settings.get("temperature", 0.0)),
            timeout_seconds=float(settings.get("timeout_seconds", 60.0)),
            include_retrieved_patterns=bool(settings.get("include_retrieved_patterns", True)),
            include_objective=bool(settings.get("include_objective", True)),
            role_provider_overrides=dict(settings.get("role_provider_overrides") or {}),
            role_model_overrides=dict(settings.get("role_model_overrides") or {}),
        )

    raise WorkerLLMError(f"unknown llm backend {backend!r}; supported: 'stub' | 'gateway'")


__all__ = [
    "WorkerLLMDispatcher", "WorkerLLMResponse", "StreamChunk",
    "StubDispatcher", "GatewayDispatcher", "WorkerLLMError",
    "StreamingHITLInterrupt",
    "build_dispatcher", "resolve_llm_settings", "estimate_call_cost",
    "DEFAULT_SETTINGS",
    "_build_user_prompt", "_extract_text", "_extract_usage",
    "_extract_model_id", "_extract_finish_reason",
    "_normalise_stream_chunk", "_env_bool",
]
