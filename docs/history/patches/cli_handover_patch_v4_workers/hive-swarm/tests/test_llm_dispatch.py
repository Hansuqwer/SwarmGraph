"""Unit tests for swarm.llm.dispatch — no network."""
from __future__ import annotations

from typing import Any

import pytest

from swarm.llm.dispatch import (
    DEFAULT_SETTINGS,
    GatewayDispatcher,
    StubDispatcher,
    WorkerLLMError,
    _build_user_prompt,
    _extract_text,
    build_dispatcher,
    resolve_llm_settings,
)
from swarm.llm.prompts import get_system_prompt


# ── settings resolution ───────────────────────────────────────────────────

def test_default_settings_are_stub():
    s = resolve_llm_settings(task_context=None, role="coder")
    assert s["backend"] == "stub"
    assert s["effective_provider"] == s["default_provider"]


def test_queen_forwarded_settings_override_defaults():
    ctx = {
        "shared_context": {
            "llm_settings": {
                "backend": "gateway",
                "default_provider": "openrouter",
                "max_tokens": 1024,
            }
        }
    }
    s = resolve_llm_settings(ctx, role="coder")
    assert s["backend"] == "gateway"
    assert s["default_provider"] == "openrouter"
    assert s["max_tokens"] == 1024


def test_env_overrides_queen_settings(monkeypatch):
    monkeypatch.setenv("HIVE_SWARM_LLM_BACKEND", "gateway")
    monkeypatch.setenv("HIVE_SWARM_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("HIVE_SWARM_LLM_MAX_TOKENS", "256")
    monkeypatch.setenv("HIVE_SWARM_LLM_TEMPERATURE", "0.7")

    ctx = {
        "shared_context": {
            "llm_settings": {
                "backend": "stub",
                "default_provider": "9router",
                "max_tokens": 512,
                "temperature": 0.0,
            }
        }
    }
    s = resolve_llm_settings(ctx, role="coder")
    assert s["backend"] == "gateway"
    assert s["default_provider"] == "deepseek"
    assert s["max_tokens"] == 256
    assert s["temperature"] == 0.7


def test_role_provider_override_applied():
    ctx = {
        "shared_context": {
            "llm_settings": {
                "backend": "gateway",
                "default_provider": "9router",
                "role_provider_overrides": {"coder": "openrouter"},
            }
        }
    }
    coder = resolve_llm_settings(ctx, role="coder")
    tester = resolve_llm_settings(ctx, role="tester")
    assert coder["effective_provider"] == "openrouter"
    assert tester["effective_provider"] == "9router"


def test_env_temperature_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("HIVE_SWARM_LLM_TEMPERATURE", "not-a-float")
    s = resolve_llm_settings(None, role="coder")
    assert s["temperature"] == DEFAULT_SETTINGS["temperature"]


def test_default_settings_immutable_to_callers():
    """resolve_llm_settings must not mutate DEFAULT_SETTINGS."""
    snapshot = dict(DEFAULT_SETTINGS)
    resolve_llm_settings({"shared_context": {"llm_settings": {"backend": "gateway"}}}, role="x")
    assert DEFAULT_SETTINGS == snapshot


# ── prompt building ──────────────────────────────────────────────────────

def test_build_user_prompt_minimal():
    out = _build_user_prompt("write add()", task_context=None)
    assert "write add()" in out


def test_build_user_prompt_includes_retrieved_patterns():
    ctx = {
        "shared_context": {
            "retrieved_patterns": [
                {"key": "k1", "value": "use type hints", "score": 0.9},
                {"key": "k2", "value": "prefer pure functions", "score": 0.8},
            ]
        }
    }
    out = _build_user_prompt("implement add", task_context=ctx)
    assert "use type hints" in out
    assert "prefer pure functions" in out
    assert "SONA memory" in out


def test_build_user_prompt_skips_retrieval_when_disabled():
    ctx = {"shared_context": {"retrieved_patterns": [{"value": "tip"}]}}
    out = _build_user_prompt(
        "task", task_context=ctx, include_retrieved_patterns=False
    )
    assert "tip" not in out


def test_build_user_prompt_includes_objective_when_distinct():
    ctx = {"shared_context": {"objective": "Build payments service"}}
    out = _build_user_prompt(
        "Implement refund endpoint",
        task_context=ctx,
        include_objective=True,
    )
    assert "Build payments service" in out


def test_build_user_prompt_skips_objective_when_already_in_task():
    ctx = {"shared_context": {"objective": "Implement refund endpoint"}}
    out = _build_user_prompt(
        "Implement refund endpoint",
        task_context=ctx,
        include_objective=True,
    )
    # Should not be duplicated
    assert out.count("Implement refund endpoint") == 1


def test_build_user_prompt_caps_pattern_count_and_length():
    ctx = {
        "shared_context": {
            "retrieved_patterns": [
                {"value": "x" * 1000, "score": 0.9} for _ in range(20)
            ]
        }
    }
    out = _build_user_prompt(
        "task", task_context=ctx, max_patterns=3, max_pattern_chars=50,
    )
    # Only 3 patterns × 50 chars max each
    assert out.count("[score=0.90]") == 3
    long_x_blocks = [line for line in out.splitlines() if "x" * 100 in line]
    assert long_x_blocks == []


# ── response extraction ──────────────────────────────────────────────────

def test_extract_text_from_string():
    assert _extract_text("hello") == "hello"


def test_extract_text_from_string_empty_raises():
    with pytest.raises(WorkerLLMError):
        _extract_text("")


def test_extract_text_from_object_with_content_attr():
    class R: content = "from-attr"
    assert _extract_text(R()) == "from-attr"


def test_extract_text_from_dict_with_content_key():
    assert _extract_text({"content": "from-dict"}) == "from-dict"


def test_extract_text_from_openai_shape():
    resp = {"choices": [{"message": {"content": "openai-style"}}]}
    assert _extract_text(resp) == "openai-style"


def test_extract_text_from_openai_reasoning_fallback():
    resp = {"choices": [{"message": {"content": "", "reasoning": "thinking"}}]}
    assert _extract_text(resp) == "thinking"


def test_extract_text_legacy_text_field():
    assert _extract_text({"choices": [{"text": "legacy"}]}) == "legacy"


def test_extract_text_message_object_with_content():
    class Msg:
        content = "object-with-content"
    class R:
        message = Msg()
    assert _extract_text(R()) == "object-with-content"


def test_extract_text_unknown_object_raises():
    class Opaque: pass
    with pytest.raises(WorkerLLMError):
        _extract_text(Opaque())


def test_extract_text_none_raises():
    with pytest.raises(WorkerLLMError):
        _extract_text(None)


# ── StubDispatcher (back-compat) ─────────────────────────────────────────

def test_stub_dispatch_matches_pre_v4_strings():
    d = StubDispatcher()
    assert d.dispatch("coder", "implement foo") == "[CODER] Implementation for: implement foo"
    assert d.dispatch("tester", "write tests for bar") == "[TESTER] Test suite for: write tests for bar"
    assert d.dispatch("documenter", "doc the thing") == "[AGENT] Output for: doc the thing"


def test_stub_dispatch_unknown_role_uses_default_template():
    d = StubDispatcher()
    out = d.dispatch("nonexistent_role", "task X")
    assert out == "[AGENT] Output for: task X"


# ── GatewayDispatcher (mocked adapter) ───────────────────────────────────

class _FakeAdapter:
    """Mimics the upstream ProviderAdapter ABC enough to satisfy the
    GatewayDispatcher's method-name fallback walk."""

    def __init__(self, *, return_value: Any = "fake-llm-output", configured: bool = True):
        self.return_value = return_value
        self._configured = configured
        self.calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self._configured

    def chat(self, *, messages, max_tokens, temperature):
        self.calls.append({
            "method": "chat",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return self.return_value


def test_gateway_dispatch_happy_path():
    fake = _FakeAdapter(return_value="hello from fake")
    d = GatewayDispatcher(
        default_provider="9router",
        adapter_factory=lambda pid: fake,
    )
    out = d.dispatch("coder", "implement add()", context=None)
    assert out == "hello from fake"
    assert len(fake.calls) == 1
    msgs = fake.calls[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == get_system_prompt("coder")
    assert msgs[1]["role"] == "user"
    assert "implement add()" in msgs[1]["content"]


def test_gateway_dispatch_passes_max_tokens_and_temperature():
    fake = _FakeAdapter()
    d = GatewayDispatcher(
        default_provider="9router",
        max_tokens=256, temperature=0.5,
        adapter_factory=lambda pid: fake,
    )
    d.dispatch("coder", "x")
    assert fake.calls[0]["max_tokens"] == 256
    assert fake.calls[0]["temperature"] == 0.5


def test_gateway_dispatch_includes_retrieved_patterns():
    fake = _FakeAdapter()
    d = GatewayDispatcher(default_provider="9router", adapter_factory=lambda pid: fake)
    ctx = {
        "shared_context": {
            "retrieved_patterns": [{"value": "use Pydantic v2 ConfigDict", "score": 0.95}]
        }
    }
    d.dispatch("coder", "implement state model", context=ctx)
    user_msg = fake.calls[0]["messages"][1]["content"]
    assert "use Pydantic v2 ConfigDict" in user_msg


def test_gateway_dispatch_role_override_picks_different_adapter():
    """Per-role override picks a different provider id; factory called accordingly."""
    seen_provider_ids: list[str] = []

    def factory(pid: str) -> _FakeAdapter:
        seen_provider_ids.append(pid)
        return _FakeAdapter(return_value=f"from-{pid}")

    d = GatewayDispatcher(
        default_provider="9router",
        role_provider_overrides={"coder": "openrouter"},
        adapter_factory=factory,
    )
    coder_out = d.dispatch("coder", "x")
    tester_out = d.dispatch("tester", "y")
    assert coder_out == "from-openrouter"
    assert tester_out == "from-9router"
    assert "openrouter" in seen_provider_ids
    assert "9router" in seen_provider_ids


def test_gateway_dispatch_unconfigured_adapter_raises():
    d = GatewayDispatcher(
        default_provider="9router",
        adapter_factory=lambda pid: _FakeAdapter(configured=False),
    )
    with pytest.raises(WorkerLLMError, match="not configured"):
        d.dispatch("coder", "x")


def test_gateway_dispatch_method_fallback_chat_completion():
    class CC:
        def is_configured(self): return True
        def chat_completion(self, *, messages, max_tokens, temperature):
            return "via-chat-completion"
    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: CC())
    assert d.dispatch("coder", "task") == "via-chat-completion"


def test_gateway_dispatch_method_fallback_complete_with_prompt_kwarg():
    class C:
        def is_configured(self): return True
        def complete(self, *, prompt, max_tokens, temperature):
            return f"complete-saw-{prompt[-10:]}"
    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: C())
    out = d.dispatch("coder", "implement add()")
    assert out.startswith("complete-saw-")


def test_gateway_dispatch_no_callable_method_raises():
    class Opaque:
        def is_configured(self): return True
    d = GatewayDispatcher(default_provider="x", adapter_factory=lambda pid: Opaque())
    with pytest.raises(WorkerLLMError, match="no callable LLM method"):
        d.dispatch("coder", "x")


def test_gateway_dispatch_adapter_factory_failure_raises_typed():
    def boom(pid):
        raise RuntimeError("simulated load failure")
    d = GatewayDispatcher(default_provider="x", adapter_factory=boom)
    with pytest.raises(WorkerLLMError, match="could not load adapter"):
        d.dispatch("coder", "x")


def test_gateway_dispatch_caches_adapter_per_provider():
    instances: list[_FakeAdapter] = []

    def factory(pid):
        a = _FakeAdapter()
        instances.append(a)
        return a

    d = GatewayDispatcher(default_provider="9router", adapter_factory=factory)
    d.dispatch("coder", "x")
    d.dispatch("tester", "y")
    d.dispatch("reviewer", "z")
    assert len(instances) == 1   # cached after first lookup


# ── build_dispatcher factory ─────────────────────────────────────────────

def test_build_dispatcher_stub_default():
    d = build_dispatcher({"backend": "stub", "effective_provider": "ignored"})
    assert isinstance(d, StubDispatcher)


def test_build_dispatcher_stub_aliases():
    for alias in ("stub", "off", "none", "false", "0", "STUB"):
        assert isinstance(build_dispatcher({"backend": alias}), StubDispatcher)


def test_build_dispatcher_gateway():
    d = build_dispatcher({
        "backend": "gateway",
        "effective_provider": "9router",
        "max_tokens": 100,
        "temperature": 0.0,
    })
    assert isinstance(d, GatewayDispatcher)
    assert d.default_provider == "9router"
    assert d.max_tokens == 100


def test_build_dispatcher_unknown_backend_raises():
    with pytest.raises(WorkerLLMError, match="unknown llm backend"):
        build_dispatcher({"backend": "magic"})


# ── prompts ─────────────────────────────────────────────────────────────

def test_get_system_prompt_known_role():
    assert "Coder" in get_system_prompt("coder")


def test_get_system_prompt_unknown_falls_back():
    out = get_system_prompt("plumber")
    assert "swarm" in out.lower()
