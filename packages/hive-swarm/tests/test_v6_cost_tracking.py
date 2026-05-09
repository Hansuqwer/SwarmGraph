"""Tests for cost tracking propagation through worker_node."""

from typing import Any

import pytest

from swarm.llm import dispatch as dispatch_mod
from swarm.models.agent import AgentState, WorkerResult, TokenUsage
from swarm.models.config import SwarmConfig
from swarm.models.task import QueenDirective, SwarmTask
from swarm.nodes.queen import _llm_settings_from_config
from swarm.nodes.worker import _to_token_usage, worker_node


# ── _to_token_usage cost branch ──────────────────────────────────────────


def test_to_token_usage_populates_cost_for_priced_model():
    """Anthropic Opus 4.7 is in the default pricing table."""
    from swarm.llm import WorkerLLMResponse

    resp = WorkerLLMResponse(
        text="x",
        backend="gateway",
        input_tokens=1000,
        output_tokens=500,
        model_id_used="claude-opus-4-7",
        finish_reason="stop",
        provider_id="anthropic",
    )
    u = _to_token_usage(resp, cost_tracking_enabled=True)
    assert u is not None
    # 1000 in @ $0.005/k + 500 out @ $0.025/k = $0.005 + $0.0125 = $0.0175
    assert u.cost_usd == pytest.approx(0.0175)


def test_to_token_usage_zero_cost_for_free_model():
    from swarm.llm import WorkerLLMResponse

    resp = WorkerLLMResponse(
        text="x",
        backend="gateway",
        input_tokens=1000,
        output_tokens=500,
        model_id_used="kc/kilo-auto/free",
        provider_id="9router",
    )
    u = _to_token_usage(resp, cost_tracking_enabled=True)
    assert u is not None
    assert u.cost_usd == 0.0


def test_to_token_usage_cost_none_for_unknown_model():
    from swarm.llm import WorkerLLMResponse

    resp = WorkerLLMResponse(
        text="x",
        backend="gateway",
        input_tokens=1000,
        output_tokens=500,
        model_id_used="unknown-vendor/secret-model",
        provider_id="???",
    )
    u = _to_token_usage(resp, cost_tracking_enabled=True)
    assert u is not None
    assert u.cost_usd is None


def test_to_token_usage_cost_none_when_tracking_disabled():
    from swarm.llm import WorkerLLMResponse

    resp = WorkerLLMResponse(
        text="x",
        backend="gateway",
        input_tokens=1000,
        output_tokens=500,
        model_id_used="claude-opus-4-7",
    )
    u = _to_token_usage(resp, cost_tracking_enabled=False)
    assert u is not None
    assert u.cost_usd is None


def test_to_token_usage_cost_none_with_zero_tokens():
    """Zero tokens → no cost computed (avoids spurious 0.0 entries)."""
    from swarm.llm import WorkerLLMResponse

    resp = WorkerLLMResponse(
        text="x",
        backend="stub",
        input_tokens=0,
        output_tokens=0,
        model_id_used="stub:deterministic",
        provider_id="stub",
    )
    u = _to_token_usage(resp, cost_tracking_enabled=True)
    assert u is not None
    assert u.cost_usd is None


# ── TokenUsage model ─────────────────────────────────────────────────────


def test_token_usage_with_cost_round_trip():
    u1 = TokenUsage(
        input_tokens=100,
        output_tokens=50,
        model_id_used="claude-opus-4-7",
        provider_id="anthropic",
        cost_usd=0.00175,
    )
    d = u1.model_dump(mode="json")
    u2 = TokenUsage.model_validate(d)
    assert u2.cost_usd == pytest.approx(0.00175)


def test_token_usage_negative_cost_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=10, output_tokens=5, cost_usd=-0.001)


def test_token_usage_default_cost_is_none():
    u = TokenUsage(input_tokens=10, output_tokens=5)
    assert u.cost_usd is None


# ── End-to-end through worker_node ───────────────────────────────────────


class _FakeAdapter:
    def __init__(self, model_id="claude-opus-4-7"):
        self.model_id = model_id

    def is_configured(self):
        return True

    def chat(self, *, messages, max_tokens, temperature, model=None):
        return {
            "model": model or self.model_id,
            "choices": [{"message": {"content": "fake-output"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }


@pytest.fixture
def fake_priced_adapter(monkeypatch):
    fake = _FakeAdapter()
    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda pid: fake,
    )
    return fake


def _make_agent(role="coder", config=None):
    cfg = config or SwarmConfig(llm_backend="gateway")
    settings = _llm_settings_from_config(cfg)
    shared = {
        "iteration": 1,
        "objective": "x",
        "retrieved_patterns": [],
        "llm_settings": settings,
    }
    swarm_task = SwarmTask(
        task_id="t1",
        description="x",
        priority="high",
        assigned_to=f"{role}-1",
        required_role=role,
    )
    swarm_task.assign(f"{role}-1")
    directive = QueenDirective(
        directive_id="dir-t1",
        task=swarm_task,
        assigned_agent_id=f"{role}-1",
        assigned_role=role,
        objective_hash="deadbeefcafebabe",
        shared_context=shared,
    )
    return AgentState(
        agent_id=f"{role}-1",
        role=role,
        assigned_task_id="t1",
        task_description="x",
        task_context=directive.model_dump(mode="json"),
    )


def test_worker_populates_cost_when_priced(fake_priced_adapter):
    cfg = SwarmConfig(
        llm_backend="gateway",
        llm_default_model="claude-opus-4-7",
        cost_tracking_enabled=True,
    )
    agent = _make_agent(config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is True
    assert r.usage is not None
    # Should have a non-None cost since claude-opus-4-7 is priced
    assert r.usage.cost_usd is not None
    assert r.usage.cost_usd > 0


def test_worker_cost_disabled_via_config(monkeypatch):
    fake = _FakeAdapter()
    monkeypatch.setattr(dispatch_mod, "_default_adapter_factory", lambda pid: fake)
    cfg = SwarmConfig(
        llm_backend="gateway",
        llm_default_model="claude-opus-4-7",
        cost_tracking_enabled=False,
    )
    agent = _make_agent(config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.usage is not None
    assert r.usage.cost_usd is None
