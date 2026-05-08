"""WorkerLLMDispatcher protocol + Stub / Gateway implementations (v5).

v5 additions (all backwards-compatible):
  - `WorkerLLMResponse` dataclass: text + token counts + model_id + finish_reason.
  - `dispatch_full(role, task, ctx) -> WorkerLLMResponse` on every dispatcher.
    Existing `dispatch(...) -> str` kept as a thin wrapper around it.
  - `llm_role_model_overrides` setting plumbed into per-call `model=` kwarg.
  - `_extract_usage(resp) -> tuple[int, int]` helper covering all 4 shapes.

v4 history preserved:
  - StubDispatcher: deterministic, no network, default for back-compat.
  - GatewayDispatcher: routes via ai-provider-swarm-gateway adapters.
  - resolve_llm_settings: env > queen > defaults precedence.
  - SONA-retrieved patterns reach the user prompt (F-27A).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .prompts import get_system_prompt


# ── Public exception ──────────────────────────────────────────────────────

class WorkerLLMError(RuntimeError):
    """Raised by any dispatcher when an LLM call fails."""


# ── Public response object (v5) ──────────────────────────────────────────

@dataclass(frozen=True)
class WorkerLLMResponse:
    """Normalised response across stub + every adapter shape.

    Always populated:
      - text: the string content (what the worker uses as `output`)
      - backend: "stub" | "gateway"
      - latency_ms: dispatcher-side wall-clock latency

    Best-effort (None / 0 if unavailable):
      - input_tokens / output_tokens
      - model_id_used: actual model the provider selected
      - finish_reason: "stop" | "length" | "reasoning_only" | ...
      - provider_id: which adapter fielded the call (gateway only)
    """
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


# ── Defaults + settings resolution ────────────────────────────────────────

DEFAULT_SETTINGS: dict[str, Any] = {
    "backend": "stub",
    "default_provider": "9router",
    "default_model": "",                     # empty → adapter default
    "max_tokens": 512,
    "temperature": 0.0,
    "timeout_seconds": 60.0,
    "role_provider_overrides": {},
    "role_model_overrides": {},              # v5: per-role model_id
    "include_retrieved_patterns": True,
    "include_objective": True,
}

_ENV_BACKEND = "HIVE_SWARM_LLM_BACKEND"
_ENV_PROVIDER = "HIVE_SWARM_LLM_PROVIDER"
_ENV_MODEL = "HIVE_SWARM_LLM_MODEL"
_ENV_MAX_TOKENS = "HIVE_SWARM_LLM_MAX_TOKENS"
_ENV_TEMPERATURE = "HIVE_SWARM_LLM_TEMPERATURE"


def resolve_llm_settings(
    task_context: dict[str, Any] | None,
    role: str | None = None,
) -> dict[str, Any]:
    """Compose effective settings. Precedence: env > queen-forwarded > DEFAULT_SETTINGS.

    Per-role overrides apply via `role_provider_overrides[role]` and
    `role_model_overrides[role]`. The resolved values are stored as
    `effective_provider` and `effective_model` for the dispatcher to consume.
    """
    settings = dict(DEFAULT_SETTINGS)

    if task_context:
        shared = task_context.get("shared_context") or {}
        if isinstance(shared, dict):
            queen_settings = shared.get("llm_settings") or {}
            if isinstance(queen_settings, dict):
                for k, v in queen_settings.items():
                    if v is not None:
                        settings[k] = v

    # Env overrides
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

    # Per-role provider override
    p_overrides = settings.get("role_provider_overrides") or {}
    if isinstance(p_overrides, dict) and role and role in p_overrides:
        settings["effective_provider"] = p_overrides[role]
    else:
        settings["effective_provider"] = settings["default_provider"]

    # v5: per-role model override
    m_overrides = settings.get("role_model_overrides") or {}
    if isinstance(m_overrides, dict) and role and role in m_overrides:
        settings["effective_model"] = m_overrides[role]
    else:
        settings["effective_model"] = settings.get("default_model") or ""

    return settings


# ── Prompt building (v4, unchanged) ──────────────────────────────────────

def _build_user_prompt(
    task_description: str,
    task_context: dict[str, Any] | None,
    *,
    include_retrieved_patterns: bool = True,
    include_objective: bool = True,
    max_pattern_chars: int = 300,
    max_patterns: int = 5,
) -> str:
    parts: list[str] = [task_description.strip()]

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


# ── Response extraction ──────────────────────────────────────────────────

_TEXT_ATTR_CANDIDATES = (
    "content", "text", "response_text", "output", "message",
    "final_response", "validated_response",
)
_DICT_KEY_CANDIDATES = (
    "content", "text", "response_text", "output", "final_response",
    "validated_response",
)


def _extract_text(resp: Any) -> str:
    """Pull a string out of any plausible adapter response shape."""
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


# ── Usage extraction (v5 NEW) ────────────────────────────────────────────

_USAGE_ATTR_CANDIDATES = ("usage", "token_usage")
_INPUT_TOKEN_KEYS = ("input_tokens", "prompt_tokens")
_OUTPUT_TOKEN_KEYS = ("output_tokens", "completion_tokens", "generated_tokens")


def _extract_usage(resp: Any) -> tuple[int, int]:
    """Return (input_tokens, output_tokens). Both 0 if unavailable."""
    if resp is None or isinstance(resp, str):
        return 0, 0

    # Object attribute walk: NineRouterResponse exposes input_tokens / output_tokens directly
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

    # Object with .usage sub-object
    for attr in _USAGE_ATTR_CANDIDATES:
        if hasattr(resp, attr):
            usage = getattr(resp, attr)
            if usage is None:
                continue
            in_t = _read_int_field(usage, _INPUT_TOKEN_KEYS)
            out_t = _read_int_field(usage, _OUTPUT_TOKEN_KEYS)
            if in_t or out_t:
                return in_t, out_t

    # Dict shape: OpenAI-compatible {"usage": {"prompt_tokens": X, ...}}
    if isinstance(resp, dict):
        for attr in _USAGE_ATTR_CANDIDATES:
            usage = resp.get(attr)
            if isinstance(usage, dict):
                in_t = _read_int_field(usage, _INPUT_TOKEN_KEYS)
                out_t = _read_int_field(usage, _OUTPUT_TOKEN_KEYS)
                if in_t or out_t:
                    return in_t, out_t
        # Top-level keys
        in_t = _read_int_field(resp, _INPUT_TOKEN_KEYS)
        out_t = _read_int_field(resp, _OUTPUT_TOKEN_KEYS)
        if in_t or out_t:
            return in_t, out_t

    return 0, 0


def _read_int_field(obj: Any, names: tuple[str, ...]) -> int:
    """Try to read an int from obj.<name> or obj[<name>] for any name in names."""
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


def _extract_model_id(resp: Any, fallback: str = "") -> str:
    """Return the actual model used (provider may have routed differently)."""
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


def _extract_finish_reason(resp: Any) -> str:
    """Best-effort finish_reason extraction."""
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


# ── Dispatcher protocol ───────────────────────────────────────────────────

class WorkerLLMDispatcher(Protocol):
    def dispatch(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> str: ...

    def dispatch_full(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> WorkerLLMResponse: ...


# ── Stub dispatcher (default, back-compat) ────────────────────────────────

_STUB_TEMPLATES: dict[str, str] = {
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
    """Deterministic stub responses — identical to pre-v4 worker stubs."""

    def __init__(self, *, max_desc_chars: int = 200) -> None:
        self.max_desc_chars = max_desc_chars

    def dispatch(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        return self.dispatch_full(role, task_description, context).text

    def dispatch_full(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> WorkerLLMResponse:
        template = _STUB_TEMPLATES.get(role, _STUB_DEFAULT)
        text = template.format(desc=task_description[: self.max_desc_chars])
        return WorkerLLMResponse(
            text=text,
            backend="stub",
            latency_ms=0,
            input_tokens=0,
            output_tokens=0,
            model_id_used="stub:deterministic",
            finish_reason="stop",
            provider_id="stub",
        )


# ── Gateway dispatcher ────────────────────────────────────────────────────

_AdapterFactory = Callable[[str], Any]


def _default_adapter_factory(provider_id: str) -> Any:
    try:
        from ai_provider_swarm_gateway.graph.nodes import _get_adapter  # type: ignore
    except ImportError as e:
        raise WorkerLLMError(
            "ai-provider-swarm-gateway is not installed; "
            "install it to use llm_backend='gateway'."
        ) from e
    return _get_adapter(provider_id)


class GatewayDispatcher:
    """Dispatch through ai-provider-swarm-gateway adapter registry."""

    _METHOD_CANDIDATES = (
        "chat", "chat_completion", "complete", "call", "invoke",
    )

    def __init__(
        self,
        *,
        default_provider: str = "9router",
        default_model: str = "",
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        include_retrieved_patterns: bool = True,
        include_objective: bool = True,
        role_provider_overrides: dict[str, str] | None = None,
        role_model_overrides: dict[str, str] | None = None,
        adapter_factory: _AdapterFactory | None = None,
    ) -> None:
        self.default_provider = default_provider
        self.default_model = default_model
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.timeout_seconds = float(timeout_seconds)
        self.include_retrieved_patterns = bool(include_retrieved_patterns)
        self.include_objective = bool(include_objective)
        self.role_provider_overrides: dict[str, str] = dict(role_provider_overrides or {})
        self.role_model_overrides: dict[str, str] = dict(role_model_overrides or {})
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._adapter_cache: dict[str, Any] = {}

    def _provider_for_role(self, role: str) -> str:
        return self.role_provider_overrides.get(role, self.default_provider)

    def _model_for_role(self, role: str) -> str:
        return self.role_model_overrides.get(role, self.default_model)

    def _ensure_adapter(self, provider_id: str) -> Any:
        if provider_id not in self._adapter_cache:
            self._adapter_cache[provider_id] = self._adapter_factory(provider_id)
        return self._adapter_cache[provider_id]

    def _call_adapter(
        self,
        adapter: Any,
        *,
        system_prompt: str,
        user_prompt: str,
        model_id: str = "",
    ) -> Any:
        """Try every plausible method signature. v5: forwards model_id when set."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs_with_model: dict[str, Any] = {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if model_id:
            kwargs_with_model["model"] = model_id

        last_err: Exception | None = None

        for name in self._METHOD_CANDIDATES:
            method = getattr(adapter, name, None)
            if not callable(method):
                continue

            # Try messages= form (preferred)
            try:
                return method(messages=messages, **kwargs_with_model)
            except TypeError as e:
                last_err = e
                # Drop model= and retry (some adapters don't accept it)
                if "model" in kwargs_with_model:
                    try:
                        kwargs_no_model = {
                            k: v for k, v in kwargs_with_model.items() if k != "model"
                        }
                        return method(messages=messages, **kwargs_no_model)
                    except TypeError as e2:
                        last_err = e2
                # Try prompt= form
                try:
                    return method(prompt=user_prompt, **{
                        k: v for k, v in kwargs_with_model.items() if k != "model"
                    })
                except TypeError as e3:
                    last_err = e3
                # Try positional
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

    # ── Dispatcher protocol ──────────────────────────────────────────────

    def dispatch(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        return self.dispatch_full(role, task_description, context).text

    def dispatch_full(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> WorkerLLMResponse:
        provider_id = self._provider_for_role(role)
        model_id = self._model_for_role(role)

        try:
            adapter = self._ensure_adapter(provider_id)
        except WorkerLLMError:
            raise
        except Exception as e:
            raise WorkerLLMError(
                f"could not load adapter {provider_id!r}: {e}"
            ) from e

        if not getattr(adapter, "is_configured", lambda: True)():
            raise WorkerLLMError(
                f"adapter {provider_id!r} is not configured "
                f"(typically missing API key env var)"
            )

        system_prompt = get_system_prompt(role)
        user_prompt = _build_user_prompt(
            task_description,
            context,
            include_retrieved_patterns=self.include_retrieved_patterns,
            include_objective=self.include_objective,
        )

        t0 = time.monotonic()
        resp = self._call_adapter(
            adapter,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_id=model_id,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        text = _extract_text(resp)
        in_tok, out_tok = _extract_usage(resp)
        actual_model = _extract_model_id(resp, fallback=model_id or "unknown")
        finish_reason = _extract_finish_reason(resp)

        return WorkerLLMResponse(
            text=text,
            backend="gateway",
            latency_ms=latency_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model_id_used=actual_model,
            finish_reason=finish_reason,
            provider_id=provider_id,
        )


# ── Factory ───────────────────────────────────────────────────────────────

def build_dispatcher(settings: dict[str, Any]) -> WorkerLLMDispatcher:
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
            include_retrieved_patterns=bool(
                settings.get("include_retrieved_patterns", True)
            ),
            include_objective=bool(settings.get("include_objective", True)),
            role_provider_overrides=dict(
                settings.get("role_provider_overrides") or {}
            ),
            role_model_overrides=dict(
                settings.get("role_model_overrides") or {}
            ),
        )

    raise WorkerLLMError(
        f"unknown llm backend {backend!r}; supported: 'stub' | 'gateway'"
    )


__all__ = [
    "WorkerLLMDispatcher",
    "WorkerLLMResponse",
    "StubDispatcher",
    "GatewayDispatcher",
    "WorkerLLMError",
    "build_dispatcher",
    "resolve_llm_settings",
    "DEFAULT_SETTINGS",
    "_build_user_prompt",
    "_extract_text",
    "_extract_usage",
    "_extract_model_id",
    "_extract_finish_reason",
]
