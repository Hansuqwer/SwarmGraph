"""Tests for v5 dispatch_full + WorkerLLMResponse + per-role model overrides."""
from __future__ import annotations

from typing import Any

import pytest

from swarm.llm.dispatch import (
    GatewayDispatcher,
    StubDispatcher,
    WorkerLLMResponse,
    _extract_finish_reason,
    _extract_model_id,
    _extract_usage,
    build_dispatcher,
    resolve_llm_settings,
)


# ── WorkerLLMResponse contract ───────────────────────────────────────────

def test_worker_llm_response_total_tokens():
    r = WorkerLLMResponse(text="x", backend="gateway", input_tokens=10, output_tokens=20)
    assert r.total_tokens == 30


def test_worker_llm_response_default_zeros():
    r = WorkerLLMResponse(text="x", backend="stub")
    assert r.input_tokens == 0
    assert r.output_tokens == 0
    assert r.total_tokens == 0


# ── StubDispatcher.dispatch_full ─────────────────────────────────────────

def test_stub_dispatch_full_returns_response_object():
    d = StubDispatcher()
    r = d.dispatch_full("coder", "implement add")
    assert isinstance(r, WorkerLLMResponse)
    assert r.backend == "stub"
    assert r.text == "[CODER] Implementation for: implement add"
    assert r.model_id_used == "stub:deterministic"
    assert r.input_tokens == 0
    assert r.output_tokens == 0
    assert r.provider_id == "stub"


def test_stub_dispatch_returns_str_unchanged():
    """Back-compat: dispatch() still returns plain str."""
    d = StubDispatcher()
    s = d.dispatch("coder", "implement add")
    assert isinstance(s, str)
    assert s == "[CODER] Implementation for: implement add"


# ── _extract_usage across shapes ─────────────────────────────────────────

def test_extract_usage_from_nine_router_attrs():
    class FakeNRR:
        input_tokens = 12
        output_tokens = 34
    in_t, out_t = _extract_usage(FakeNRR())
    assert in_t == 12
    assert out_t == 34


def test_extract_usage_from_openai_dict():
    resp = {"usage": {"prompt_tokens": 50, "completion_tokens": 100}}
    in_t, out_t = _extract_usage(resp)
    assert in_t == 50
    assert out_t == 100


def test_extract_usage_from_object_with_usage_subfield():
    class Usage:
        prompt_tokens = 7
        completion_tokens = 11
    class Resp:
        usage = Usage()
    in_t, out_t = _extract_usage(Resp())
    assert in_t == 7
    assert out_t == 11


def test_extract_usage_returns_zeros_when_absent():
    in_t, out_t = _extract_usage({"choices": [{"message": {"content": "x"}}]})
    assert (in_t, out_t) == (0, 0)


def test_extract_usage_handles_none_and_str():
    assert _extract_usage(None) == (0, 0)
    assert _extract_usage("plain string") == (0, 0)


def test_extract_usage_token_usage_alias():
    """Some adapters expose .token_usage instead of .usage."""
    class U:
        input_tokens = 3
        output_tokens = 5
    class R:
        token_usage = U()
    assert _extract_usage(R()) == (3, 5)


def test_extract_usage_top_level_dict_keys():
    resp = {"input_tokens": 9, "output_tokens": 11}
    assert _extract_usage(resp) == (9, 11)


# ── _extract_model_id + _extract_finish_reason ───────────────────────────

def test_extract_model_id_from_attr():
    class R:
        model_actually_used = "stepfun/step-3.5-flash:free"
    assert _extract_model_id(R()) == "stepfun/step-3.5-flash:free"


def test_extract_model_id_falls_back_to_arg():
    assert _extract_model_id({}, fallback="default-model") == "default-model"


def test_extract_finish_reason_from_choices():
    resp = {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}
    assert _extract_finish_reason(resp) == "stop"


def test_extract_finish_reason_default_empty():
    assert _extract_finish_reason({}) == ""


# ── Per-role model resolution (v5) ───────────────────────────────────────

def test_role_model_override_applied():
    ctx = {
        "shared_context": {
            "llm_settings": {
                "backend": "gateway",
                "default_provider": "9router",
                "default_model": "kc/kilo-auto/free",
                "role_model_overrides": {
                    "coder": "anthropic/claude-opus-4-7",
                    "tester": "openai/gpt-4o-mini",
                },
            }
        }
    }
    coder = resolve_llm_settings(ctx, role="coder")
    tester = resolve_llm_settings(ctx, role="tester")
    reviewer = resolve_llm_settings(ctx, role="reviewer")

    assert coder["effective_model"] == "anthropic/claude-opus-4-7"
    assert tester["effective_model"] == "openai/gpt-4o-mini"
    assert reviewer["effective_model"] == "kc/kilo-auto/free"   # falls to default


def test_default_model_empty_means_adapter_default():
    ctx = {
        "shared_context": {
            "llm_settings": {
                "backend": "gateway",
                "default_provider": "9router",
            }
        }
    }
    s = resolve_llm_settings(ctx, role="coder")
    assert s["effective_model"] == ""   # empty → adapter chooses


def test_env_model_override(monkeypatch):
    monkeypatch.setenv("HIVE_SWARM_LLM_MODEL", "via-env-model")
    s = resolve_llm_settings(None, role="coder")
    assert s["default_model"] == "via-env-model"
    assert s["effective_model"] == "via-env-model"


def test_role_override_beats_env(monkeypatch):
    monkeypatch.setenv("HIVE_SWARM_LLM_MODEL", "env-model")
    ctx = {
        "shared_context": {
            "llm_settings": {
                "role_model_overrides": {"coder": "role-model"},
            }
        }
    }
    s = resolve_llm_settings(ctx, role="coder")
    # default_model comes from env, but role override wins for "coder"
    assert s["effective_model"] == "role-model"


# ── GatewayDispatcher.dispatch_full with mocked adapter ──────────────────

class _FakeAdapter:
    def __init__(self, *, model_seen: list[str] | None = None):
        self.model_seen = model_seen if model_seen is not None else []
        self._configured = True

    def is_configured(self) -> bool:
        return self._configured

    def chat(self, *, messages, max_tokens, temperature, model=None):
        self.model_seen.append(model or "")
        return {
            "model": model or "kc/kilo-auto/free",
            "choices": [{"message": {"content": "fake-output"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 25, "completion_tokens": 7},
        }


def test_gateway_dispatch_full_returns_typed_response():
    fake = _FakeAdapter()
    d = GatewayDispatcher(default_provider="9router", adapter_factory=lambda pid: fake)
    r = d.dispatch_full("coder", "implement add")
    assert isinstance(r, WorkerLLMResponse)
    assert r.backend == "gateway"
    assert r.text == "fake-output"
    assert r.input_tokens == 25
    assert r.output_tokens == 7
    assert r.total_tokens == 32
    assert r.finish_reason == "stop"
    assert r.provider_id == "9router"
    assert r.model_id_used   # at minimum the fallback is set


def test_gateway_dispatch_passes_per_role_model():
    fake = _FakeAdapter()
    d = GatewayDispatcher(
        default_provider="9router",
        default_model="kc/kilo-auto/free",
        role_model_overrides={"coder": "anthropic/claude-opus-4-7"},
        adapter_factory=lambda pid: fake,
    )
    d.dispatch_full("coder", "x")
    d.dispatch_full("tester", "y")
    assert fake.model_seen == ["anthropic/claude-opus-4-7", "kc/kilo-auto/free"]


def test_gateway_dispatch_no_model_when_unset():
    """Adapter that doesn't accept model= still works; we drop the kwarg."""
    class AdapterNoModel:
        def is_configured(self): return True
        def chat(self, *, messages, max_tokens, temperature):
            return "ok"

    d = GatewayDispatcher(
        default_provider="x",
        default_model="some-model",
        adapter_factory=lambda pid: AdapterNoModel(),
    )
    r = d.dispatch_full("coder", "task")
    assert r.text == "ok"


# ── build_dispatcher passes role_model_overrides through ────────────────

def test_build_dispatcher_gateway_with_role_models():
    d = build_dispatcher({
        "backend": "gateway",
        "effective_provider": "9router",
        "effective_model": "kc/kilo-auto/free",
        "role_model_overrides": {"coder": "anthropic/claude-opus-4-7"},
    })
    assert isinstance(d, GatewayDispatcher)
    assert d.role_model_overrides == {"coder": "anthropic/claude-opus-4-7"}
    assert d.default_model == "kc/kilo-auto/free"
