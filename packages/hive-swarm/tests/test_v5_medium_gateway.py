"""Tests for medium_agent_node (Tier-2) routed through the gateway."""

from __future__ import annotations

from typing import Any

import pytest

from swarm.llm import dispatch as dispatch_mod
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState
from swarm.nodes.queen import medium_agent_node


class _FakeAdapter:
    def __init__(self, return_text="MEDIUM-LLM:fake-result"):
        self.return_text = return_text
        self.calls: list[dict[str, Any]] = []

    def is_configured(self):
        return True

    def chat(self, *, messages, max_tokens, temperature, model=None):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "model": model,
            }
        )
        return {
            "model": model or "kc/kilo-auto/free",
            "choices": [{"message": {"content": self.return_text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 18, "completion_tokens": 6},
        }


def test_medium_stub_mode_unchanged():
    """SwarmConfig() default → tier-2 still emits the v4 stub label."""
    cfg = SwarmConfig()
    state = SwarmState(swarm_id="s1", objective="implement add", config=cfg)
    out = medium_agent_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)
    assert final.status == "completed"
    assert final.final_output.startswith("[MEDIUM] Single-agent result for:")


def test_medium_gateway_mode_calls_llm(monkeypatch):
    fake = _FakeAdapter(return_text="def add(a,b): return a+b")
    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda pid: fake,
    )
    cfg = SwarmConfig(llm_backend="gateway")
    state = SwarmState(swarm_id="s1", objective="Implement add", config=cfg)
    out = medium_agent_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)
    assert final.status == "completed"
    assert final.final_output == "def add(a,b): return a+b"
    # Adapter received the call
    assert len(fake.calls) == 1
    msgs = fake.calls[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "Implement add" in msgs[1]["content"]


def test_medium_gateway_mode_history_records_tokens(monkeypatch):
    fake = _FakeAdapter()
    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda pid: fake,
    )
    cfg = SwarmConfig(llm_backend="gateway")
    state = SwarmState(swarm_id="s1", objective="implement add", config=cfg)
    out = medium_agent_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)
    last_history = final.history[-1]
    assert last_history["kind"] == "worker_result"
    assert last_history["tier"] == "tier2_medium"
    assert last_history["llm_backend"] == "gateway"
    assert last_history["input_tokens"] == 18
    assert last_history["output_tokens"] == 6


def test_medium_gateway_mode_failure_routes_to_failed(monkeypatch):
    """Adapter raises → swarm.fail('model_error')."""

    class Boom:
        def is_configured(self):
            return True

        def chat(self, **kw):
            raise RuntimeError("upstream 503")

    monkeypatch.setattr(dispatch_mod, "_default_adapter_factory", lambda pid: Boom())
    cfg = SwarmConfig(llm_backend="gateway")
    state = SwarmState(swarm_id="s1", objective="x", config=cfg)
    out = medium_agent_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)
    assert final.status == "failed"
    assert final.failure_cause == "model_error"
    assert any("upstream 503" in e for e in final.errors)


def test_medium_gateway_mode_unconfigured_adapter_routes_to_failed(monkeypatch):
    class Unc:
        def is_configured(self):
            return False

    monkeypatch.setattr(dispatch_mod, "_default_adapter_factory", lambda pid: Unc())
    cfg = SwarmConfig(llm_backend="gateway")
    state = SwarmState(swarm_id="s1", objective="x", config=cfg)
    out = medium_agent_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)
    assert final.status == "failed"
    assert "not configured" in final.errors[-1]


def test_medium_uses_role_coder_for_dispatch(monkeypatch):
    """medium_agent_node uses role='coder' as the generalist persona."""
    fake = _FakeAdapter()
    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda pid: fake,
    )
    cfg = SwarmConfig(
        llm_backend="gateway",
        llm_role_model_overrides={"coder": "specific-coder-model"},
    )
    state = SwarmState(swarm_id="s1", objective="x", config=cfg)
    medium_agent_node(state.to_json_dict())
    assert fake.calls[0]["model"] == "specific-coder-model"
