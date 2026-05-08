"""WorkerLLMDispatcher protocol + Stub / Gateway implementations.

Design:
- Stub mode (default) returns deterministic role-tagged strings. Identical
  to the pre-v4 worker.py behaviour. Zero network, zero new deps.
- Gateway mode lazy-imports `ai_provider_swarm_gateway.graph.nodes._get_adapter`
  and routes through any registered adapter (default: "9router").
- Settings travel through `task_context["shared_context"]["llm_settings"]`
  (queen forwards `SwarmConfig.llm_*` fields). Env vars override.
- Adapter calls try a sequence of method names so the dispatcher works
  across upstream graph variants: chat → chat_completion → complete → call → invoke.
- Response extraction tolerates: NineRouterResponse, upstream GatewayResponse,
  OpenAI-shape dicts, plain strings.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Protocol

from .prompts import get_system_prompt


# ── Public exception ──────────────────────────────────────────────────────

class WorkerLLMError(RuntimeError):
    """Raised by any dispatcher when an LLM call fails. The worker_node
    catches this and produces a WorkerResult(success=False, error_message=...)."""


# ── Defaults + settings resolution ────────────────────────────────────────

DEFAULT_SETTINGS: dict[str, Any] = {
    "backend": "stub",                       # "stub" | "gateway"
    "default_provider": "9router",
    "max_tokens": 512,
    "temperature": 0.0,
    "timeout_seconds": 60.0,
    "role_provider_overrides": {},           # e.g. {"coder": "openrouter"}
    "include_retrieved_patterns": True,
    "include_objective": True,
}

_ENV_BACKEND = "HIVE_SWARM_LLM_BACKEND"
_ENV_PROVIDER = "HIVE_SWARM_LLM_PROVIDER"
_ENV_MAX_TOKENS = "HIVE_SWARM_LLM_MAX_TOKENS"
_ENV_TEMPERATURE = "HIVE_SWARM_LLM_TEMPERATURE"


def resolve_llm_settings(
    task_context: dict[str, Any] | None,
    role: str | None = None,
) -> dict[str, Any]:
    """Compose the effective settings. Precedence (highest first):

       1. Env vars (HIVE_SWARM_LLM_*)
       2. task_context["shared_context"]["llm_settings"]  (queen-forwarded)
       3. DEFAULT_SETTINGS

    Per-role provider overrides apply via `role_provider_overrides[role]`.
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
    env_backend = os.environ.get(_ENV_BACKEND)
    if env_backend:
        settings["backend"] = env_backend.strip().lower()
    env_provider = os.environ.get(_ENV_PROVIDER)
    if env_provider:
        settings["default_provider"] = env_provider.strip()
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

    # Per-role provider override → resolve the effective provider for this call
    overrides = settings.get("role_provider_overrides") or {}
    if isinstance(overrides, dict) and role and role in overrides:
        settings["effective_provider"] = overrides[role]
    else:
        settings["effective_provider"] = settings["default_provider"]

    return settings


# ── Prompt building ───────────────────────────────────────────────────────

def _build_user_prompt(
    task_description: str,
    task_context: dict[str, Any] | None,
    *,
    include_retrieved_patterns: bool = True,
    include_objective: bool = True,
    max_pattern_chars: int = 300,
    max_patterns: int = 5,
) -> str:
    """Assemble the user-side prompt. Includes:

       - The task description (always)
       - SONA-retrieved patterns from task_context["shared_context"]["retrieved_patterns"]
         (closes F-27A end-to-end: patterns now influence the LLM call)
       - The overall swarm objective (when distinct from the task)
    """
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

    # Object attribute walk
    for attr in _TEXT_ATTR_CANDIDATES:
        if not hasattr(resp, attr):
            continue
        v = getattr(resp, attr)
        if isinstance(v, str) and v.strip():
            return v
        # `message` may be an object/dict with a .content field
        if v is not None:
            if hasattr(v, "content") and isinstance(v.content, str) and v.content.strip():
                return v.content
            if isinstance(v, dict):
                inner = v.get("content")
                if isinstance(inner, str) and inner.strip():
                    return inner

    # Dict shape (raw OpenAI-compatible response)
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

    # Last-ditch: stringification (rejected if it's an object repr)
    s = str(resp)
    if s.startswith("<") and s.endswith(">"):
        raise WorkerLLMError(
            f"could not extract text from response of type {type(resp).__name__}"
        )
    return s


# ── Dispatcher protocol ───────────────────────────────────────────────────

class WorkerLLMDispatcher(Protocol):
    """Anything callable in this shape is a valid dispatcher."""

    def dispatch(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> str: ...


# ── Stub dispatcher (default, back-compat) ────────────────────────────────

# Identical wording to pre-v4 worker.py stubs so existing tests are unaffected.
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
        template = _STUB_TEMPLATES.get(role, _STUB_DEFAULT)
        return template.format(desc=task_description[: self.max_desc_chars])


# ── Gateway dispatcher (real LLM via ai-provider-swarm-gateway) ──────────

_AdapterFactory = Callable[[str], Any]


def _default_adapter_factory(provider_id: str) -> Any:
    """Lazy import — only triggered when GatewayDispatcher.dispatch() is called.

    Stub-mode users without ai-provider-swarm-gateway installed never hit this.
    """
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

    def __init__(
        self,
        *,
        default_provider: str = "9router",
        max_tokens: int = 512,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        include_retrieved_patterns: bool = True,
        include_objective: bool = True,
        role_provider_overrides: dict[str, str] | None = None,
        adapter_factory: _AdapterFactory | None = None,
    ) -> None:
        self.default_provider = default_provider
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.timeout_seconds = float(timeout_seconds)
        self.include_retrieved_patterns = bool(include_retrieved_patterns)
        self.include_objective = bool(include_objective)
        self.role_provider_overrides: dict[str, str] = dict(role_provider_overrides or {})
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._adapter_cache: dict[str, Any] = {}

    # ── adapter access ────────────────────────────────────────────────────

    def _provider_for_role(self, role: str) -> str:
        return self.role_provider_overrides.get(role, self.default_provider)

    def _ensure_adapter(self, provider_id: str) -> Any:
        if provider_id not in self._adapter_cache:
            self._adapter_cache[provider_id] = self._adapter_factory(provider_id)
        return self._adapter_cache[provider_id]

    # ── single-shot call with method-name fallback ───────────────────────

    _METHOD_CANDIDATES = (
        "chat", "chat_completion", "complete", "call", "invoke",
    )

    def _call_adapter(
        self,
        adapter: Any,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Any:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_err: Exception | None = None

        for name in self._METHOD_CANDIDATES:
            method = getattr(adapter, name, None)
            if not callable(method):
                continue

            # First try the messages= form (preferred for OpenAI-compatible adapters)
            try:
                return method(
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
            except TypeError as e:
                last_err = e
                # Method exists but kwargs differ; try the prompt= form
                try:
                    return method(
                        prompt=user_prompt,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
                except TypeError as e2:
                    last_err = e2
                    # Try positional
                    try:
                        return method(user_prompt)
                    except Exception as e3:
                        last_err = e3
                        continue
            except Exception as e:
                # Non-signature failure (network, auth, ...) — bubble up immediately
                raise WorkerLLMError(
                    f"adapter {type(adapter).__name__}.{name}() raised: {e}"
                ) from e

        raise WorkerLLMError(
            f"no callable LLM method on adapter {type(adapter).__name__} "
            f"(tried: {', '.join(self._METHOD_CANDIDATES)}); last error: {last_err}"
        )

    # ── dispatcher protocol ───────────────────────────────────────────────

    def dispatch(
        self,
        role: str,
        task_description: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        provider_id = self._provider_for_role(role)
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
        )
        # Extraction may itself raise WorkerLLMError
        text = _extract_text(resp)
        # (Latency observable via worker_node duration_seconds — no need to
        # return; left for future telemetry.)
        _ = time.monotonic() - t0
        return text


# ── Factory ───────────────────────────────────────────────────────────────

def build_dispatcher(settings: dict[str, Any]) -> WorkerLLMDispatcher:
    """Construct the right dispatcher from resolved settings."""
    backend = (settings.get("backend") or "stub").lower()

    if backend in ("stub", "off", "none", "false", "0"):
        return StubDispatcher()

    if backend == "gateway":
        provider = (
            settings.get("effective_provider")
            or settings.get("default_provider")
            or "9router"
        )
        return GatewayDispatcher(
            default_provider=provider,
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
        )

    raise WorkerLLMError(
        f"unknown llm backend {backend!r}; supported: 'stub' | 'gateway'"
    )


__all__ = [
    "WorkerLLMDispatcher",
    "StubDispatcher",
    "GatewayDispatcher",
    "WorkerLLMError",
    "build_dispatcher",
    "resolve_llm_settings",
    "DEFAULT_SETTINGS",
    "_build_user_prompt",   # exposed for tests
    "_extract_text",        # exposed for tests
]
