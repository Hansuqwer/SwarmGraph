"""Tests for TokenUsage propagation through worker_node into WorkerResult."""
from __future__ import annotations

from typing import Any

import pytest

from swarm.llm import dispatch as dispatch_mod
from swarm.models.agent import AgentState, TokenUsage, WorkerResult
from swarm.models.config import SwarmConfig
from swarm.models.task import QueenDirective, SwarmTask
from swarm.nodes.queen import _llm_settings_from_config
from swarm.nodes.worker import _to_token_usage, worker_node


# ── TokenUsage model ─────────────────────────────────────────────────────

def test_token_usage_defaults():
    u = TokenUsage()
    assert u.input_tokens == 0
    assert u.output_tokens == 0
    assert u.total_tokens == 0


def test_token_usage_rejects_negative():
    with pytest.raises(Exception):
        TokenUsage(input_tokens=-1)


def test_token_usage_total():
    u = TokenUsage(input_tokens=100, output_tokens=200)
    assert u.total_tokens == 300


def test_token_usage_serializable():
    u = TokenUsage(input_tokens=5, output_tokens=7, model_id_used="m", finish_reason="stop")
    d = u.model_dump(mode="json")
    assert d == {
        "input_tokens": 5, "output_tokens": 7,
        "model_id_used": "m", "finish_reason": "stop", "provider_id": "",
    }


# ── WorkerResult.usage ───────────────────────────────────────────────────

def test_worker_result_usage_optional():
    r = WorkerResult(
        agent_id="a1", agent_role="coder", task_id="t1",
        success=True, output="ok", confidence=0.9,
    )
    assert r.usage is None


def test_worker_result_with_usage():
    r = WorkerResult(
        agent_id="a1", agent_role="coder", task_id="t1",
        success=True, output="ok", confidence=0.9,
        usage=TokenUsage(input_tokens=10, output_tokens=5, model_id_used="m"),
    )
    assert r.usage is not None
    assert r.usage.total_tokens == 15


def test_worker_result_round_trip_with_usage():
    r1 = WorkerResult(
        agent_id="a1", agent_role="coder", task_id="t1",
        success=True, output="ok", confidence=0.9,
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )
    d = r1.model_dump(mode="json")
    r2 = WorkerResult.model_validate(d)
    assert r2.usage is not None
    assert r2.usage.input_tokens == 10
    assert r2.usage.output_tokens == 5


# ── _to_token_usage helper ───────────────────────────────────────────────

def test_to_token_usage_from_response_object():
    from swarm.llm import WorkerLLMResponse
    resp = WorkerLLMResponse(
        text="x", backend="gateway",
        input_tokens=12, output_tokens=34,
        model_id_used="kc/kilo-auto/free", finish_reason="stop",
        provider_id="9router",
    )
    u = _to_token_usage(resp)
    assert u is not None
    assert u.input_tokens == 12
    assert u.output_tokens == 34
    assert u.model_id_used == "kc/kilo-auto/free"
    assert u.finish_reason == "stop"
    assert u.provider_id == "9router"


def test_to_token_usage_returns_none_for_empty_response():
    from swarm.llm import WorkerLLMResponse
    resp = WorkerLLMResponse(text="x", backend="stub")
    # Stub: no token data, no model id, no provider — _to_token_usage returns None
    u = _to_token_usage(resp)
    # Stub does fill model_id_used="stub:deterministic" + provider_id="stub",
    # so usage will be non-None — verify the meaningful-content check works
    # by calling with a truly empty response:
    empty = WorkerLLMResponse(text="x", backend="custom")
    assert _to_token_usage(empty) is None


def test_to_token_usage_handles_none():
    assert _to_token_usage(None) is None


# ── End-to-end through worker_node ───────────────────────────────────────

class _FakeAdapter:
    def __init__(self, return_text="from-fake", in_tokens=20, out_tokens=8):
        self.return_text = return_text
        self.in_tokens = in_tokens
        self.out_tokens = out_tokens
        self.calls: list[dict[str, Any]] = []

    def is_configured(self): return True

    def chat(self, *, messages, max_tokens, temperature, model=None):
        self.calls.append({"messages": messages, "model": model})
        return {
            "model": model or "kc/kilo-auto/free",
            "choices": [{"message": {"content": self.return_text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": self.in_tokens, "completion_tokens": self.out_tokens},
        }


@pytest.fixture
def patch_adapter(monkeypatch):
    fake = _FakeAdapter()
    monkeypatch.setattr(
        dispatch_mod, "_default_adapter_factory",
        lambda pid: fake,
    )
    return fake


def _make_agent(role="coder", task="implement add", config=None):
    cfg = config or SwarmConfig(llm_backend="gateway")
    settings = _llm_settings_from_config(cfg)
    shared = {
        "iteration": 1,
        "objective": "Implement an add function",
        "retrieved_patterns": [],
        "llm_settings": settings,
    }
    swarm_task = SwarmTask(
        task_id="t1", description=task, priority="high",
        assigned_to=f"{role}-1", required_role=role,
    )
    swarm_task.assign(f"{role}-1")
    directive = QueenDirective(
        directive_id="dir-t1", task=swarm_task,
        assigned_agent_id=f"{role}-1", assigned_role=role,
        objective_hash="deadbeefcafebabe",
        shared_context=shared,
    )
    return AgentState(
        agent_id=f"{role}-1", role=role,
        assigned_task_id="t1", task_description=task,
        task_context=directive.model_dump(mode="json"),
    )


def test_worker_populates_usage_from_gateway_response(patch_adapter):
    agent = _make_agent()
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is True
    assert r.usage is not None
    assert r.usage.input_tokens == 20
    assert r.usage.output_tokens == 8
    assert r.usage.provider_id == "9router"


def test_worker_stub_mode_usage_is_stub_metadata(monkeypatch):
    """Stub returns model_id_used='stub:deterministic' so usage is non-None."""
    cfg = SwarmConfig()  # default: stub
    agent = _make_agent(config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is True
    # Stub fills model_id_used and provider_id, so usage is populated even in stub mode
    assert r.usage is not None
    assert r.usage.model_id_used == "stub:deterministic"
    assert r.usage.input_tokens == 0
    assert r.usage.output_tokens == 0


def test_worker_metadata_includes_latency(patch_adapter):
    agent = _make_agent()
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert "llm_latency_ms" in r.metadata
    assert isinstance(r.metadata["llm_latency_ms"], int)


def test_role_model_override_reaches_adapter(patch_adapter):
    cfg = SwarmConfig(
        llm_backend="gateway",
        llm_default_provider="9router",
        llm_role_model_overrides={"coder": "anthropic/claude-opus-4-7"},
    )
    agent = _make_agent(role="coder", config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is True
    # The fake adapter recorded the model kwarg
    assert patch_adapter.calls[0]["model"] == "anthropic/claude-opus-4-7"
