"""End-to-end worker_node tests with the gateway path mocked.

No network. We monkeypatch swarm.llm.dispatch._default_adapter_factory so
the worker_node, when it builds a GatewayDispatcher, gets a deterministic
fake adapter.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from swarm.llm import dispatch as dispatch_mod
from swarm.models.agent import AgentState, WorkerResult
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState
from swarm.models.task import QueenDirective, SwarmTask
from swarm.nodes.queen import _llm_settings_from_config, queen_node
from swarm.nodes.worker import _estimate_confidence, collect_results_node, worker_node


# ── Fake adapter wired into the gateway path ─────────────────────────────


class _FakeAdapter:
    def __init__(self, return_value: str = "GATEWAY:hello", configured: bool = True):
        self.return_value = return_value
        self._configured = configured
        self.calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self._configured

    def chat(self, *, messages, max_tokens, temperature):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return self.return_value


@pytest.fixture
def fake_gateway_adapter(monkeypatch):
    fake = _FakeAdapter()
    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda provider_id: fake,
    )
    return fake


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_agent_state(
    *,
    role: str = "coder",
    task: str = "implement add(a,b)",
    config: SwarmConfig | None = None,
    retrieved_patterns: list[dict] | None = None,
) -> AgentState:
    cfg = config or SwarmConfig()
    settings = _llm_settings_from_config(cfg)
    shared = {
        "iteration": 1,
        "objective": "Implement an add function",
        "retrieved_patterns": retrieved_patterns or [],
        "llm_settings": settings,
    }
    swarm_task = SwarmTask(
        task_id="t1",
        description=task,
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
        task_description=task,
        task_context=directive.model_dump(mode="json"),
    )


# ── Default behaviour: stub mode (back-compat) ───────────────────────────


def test_worker_node_default_stub_unchanged():
    """SwarmConfig() with no args ⇒ same string format as pre-v4."""
    agent = _make_agent_state(role="coder", task="implement add")
    out = worker_node(agent.to_json_dict())
    assert "worker_results" in out
    results = out["worker_results"]
    assert len(results) == 1
    r = WorkerResult.model_validate(results[0])
    assert r.success is True
    assert r.output.startswith("[CODER] Implementation for:")
    # metadata records backend
    assert r.metadata.get("llm_backend") == "stub"


def test_worker_node_returns_reducer_friendly_shape():
    """F-16A: shape must be {"worker_results": [dict]} (single-item list)."""
    agent = _make_agent_state()
    out = worker_node(agent.to_json_dict())
    assert set(out.keys()) == {"worker_results"}
    assert isinstance(out["worker_results"], list)
    assert len(out["worker_results"]) == 1


# ── Gateway mode end-to-end ──────────────────────────────────────────────


def test_worker_node_gateway_mode_uses_adapter(fake_gateway_adapter):
    cfg = SwarmConfig(llm_backend="gateway", llm_default_provider="9router")
    agent = _make_agent_state(role="coder", task="implement add(a,b)", config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is True
    assert r.output == "GATEWAY:hello"
    assert r.metadata.get("llm_backend") == "gateway"
    assert r.metadata.get("llm_provider") == "9router"
    # Adapter received our system + user messages
    assert len(fake_gateway_adapter.calls) == 1
    msgs = fake_gateway_adapter.calls[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "implement add(a,b)" in msgs[1]["content"]


def test_worker_node_gateway_includes_retrieved_patterns(fake_gateway_adapter):
    """F-27A end-to-end: SONA patterns reach the LLM user prompt."""
    cfg = SwarmConfig(llm_backend="gateway")
    agent = _make_agent_state(
        config=cfg,
        retrieved_patterns=[
            {"key": "k1", "value": "always use ConfigDict(extra='forbid')", "score": 0.95},
        ],
    )
    worker_node(agent.to_json_dict())
    user_msg = fake_gateway_adapter.calls[0]["messages"][1]["content"]
    assert "ConfigDict(extra='forbid')" in user_msg


def test_worker_node_env_override_forces_gateway(monkeypatch, fake_gateway_adapter):
    """HIVE_SWARM_LLM_BACKEND=gateway overrides a stub-config swarm."""
    monkeypatch.setenv("HIVE_SWARM_LLM_BACKEND", "gateway")
    cfg = SwarmConfig()  # config says stub; env wins
    agent = _make_agent_state(config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is True
    assert r.output == "GATEWAY:hello"


def test_worker_node_role_override_routes_through_alt_provider(monkeypatch):
    """Role-specific provider override picks the correct adapter id."""
    seen: list[str] = []

    def factory(pid):
        seen.append(pid)
        return _FakeAdapter(return_value=f"FROM:{pid}")

    monkeypatch.setattr(dispatch_mod, "_default_adapter_factory", factory)

    cfg = SwarmConfig(
        llm_backend="gateway",
        llm_default_provider="9router",
        llm_role_provider_overrides={"coder": "openrouter"},
    )
    coder_state = _make_agent_state(role="coder", config=cfg)
    out = worker_node(coder_state.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.output == "FROM:openrouter"

    tester_state = _make_agent_state(role="tester", config=cfg)
    out = worker_node(tester_state.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.output == "FROM:9router"


def test_worker_node_unconfigured_adapter_produces_failed_result(monkeypatch):
    """Adapter says is_configured=False ⇒ worker emits success=False, not crash."""
    monkeypatch.setattr(
        dispatch_mod,
        "_default_adapter_factory",
        lambda pid: _FakeAdapter(configured=False),
    )
    cfg = SwarmConfig(llm_backend="gateway")
    agent = _make_agent_state(config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is False
    assert "not configured" in r.error_message
    assert r.confidence == 0.0


def test_worker_node_adapter_raising_runtime_error_becomes_failed_result(monkeypatch):
    class Boom:
        def is_configured(self):
            return True

        def chat(self, **kw):
            raise RuntimeError("upstream 500")

    monkeypatch.setattr(dispatch_mod, "_default_adapter_factory", lambda pid: Boom())
    cfg = SwarmConfig(llm_backend="gateway")
    agent = _make_agent_state(config=cfg)
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is False
    assert "upstream 500" in r.error_message


def test_worker_node_unknown_backend_becomes_failed_result(monkeypatch):
    """Bogus backend value → typed WorkerResult, not exception."""
    monkeypatch.setenv("HIVE_SWARM_LLM_BACKEND", "magic")
    agent = _make_agent_state()
    out = worker_node(agent.to_json_dict())
    r = WorkerResult.model_validate(out["worker_results"][0])
    assert r.success is False
    assert "unknown llm backend" in r.error_message


# ── queen forwards llm_settings ─────────────────────────────────────────


def test_queen_forwards_llm_settings_into_directive():
    cfg = SwarmConfig(
        llm_backend="gateway",
        llm_default_provider="9router",
        llm_max_tokens=128,
        llm_temperature=0.3,
    )
    state = SwarmState(
        swarm_id="s1",
        objective="Implement add()",
        config=cfg,
    )
    sends = queen_node(state.to_json_dict())
    # Either Send objects or plain dict (depending on langgraph availability)
    payloads = []
    for s in sends:
        if isinstance(s, dict):
            payloads.append(s)
        elif hasattr(s, "arg"):  # langgraph.types.Send
            payloads.append(s.arg)
        elif isinstance(s, (list, tuple)) and len(s) >= 2:
            payloads.append(s[1])

    # At least one worker payload should carry llm_settings
    found_settings = False
    for p in payloads:
        if not isinstance(p, dict):
            continue
        ctx = p.get("task_context") or {}
        shared = ctx.get("shared_context") or {}
        ls = shared.get("llm_settings") or {}
        if ls.get("backend") == "gateway" and ls.get("default_provider") == "9router":
            found_settings = True
            assert ls.get("max_tokens") == 128
            assert ls.get("temperature") == 0.3
            break
    assert found_settings, "queen did not forward llm_settings into worker payloads"


def test_queen_default_config_forwards_stub_settings():
    cfg = SwarmConfig()
    state = SwarmState(swarm_id="s1", objective="x", config=cfg)
    sends = queen_node(state.to_json_dict())
    # We only need to confirm the field is present and == "stub"
    payloads = []
    for s in sends:
        if isinstance(s, dict):
            payloads.append(s)
        elif hasattr(s, "arg"):
            payloads.append(s.arg)
        elif isinstance(s, (list, tuple)) and len(s) >= 2:
            payloads.append(s[1])
    for p in payloads:
        if not isinstance(p, dict):
            continue
        ctx = p.get("task_context") or {}
        shared = ctx.get("shared_context") or {}
        ls = shared.get("llm_settings") or {}
        if ls:
            assert ls["backend"] == "stub"
            return
    pytest.fail("no llm_settings found in any payload")


# ── confidence helper untouched (regression) ─────────────────────────────


def test_estimate_confidence_empty_output_zero():
    assert _estimate_confidence("", "task") == 0.0


def test_estimate_confidence_in_unit_range():
    c = _estimate_confidence("implement add returning a + b", "implement add(a, b)")
    assert 0.0 <= c <= 1.0


# ── fan-in unchanged (regression) ────────────────────────────────────────


def test_collect_results_node_marks_tasks_complete():
    cfg = SwarmConfig()
    state = SwarmState(swarm_id="s1", objective="x", config=cfg)
    state.tasks.append(
        SwarmTask(task_id="t1", description="x", status="assigned", assigned_to="a1")
    )
    state.worker_results = [
        WorkerResult(
            agent_id="a1",
            agent_role="coder",
            task_id="t1",
            success=True,
            output="ok",
            confidence=0.9,
        )
    ]
    out = collect_results_node(state.to_json_dict())
    final = SwarmState.from_json_dict(out)
    assert "t1" in final.completed_task_ids
