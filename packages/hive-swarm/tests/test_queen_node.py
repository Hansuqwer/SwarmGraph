from __future__ import annotations

from langgraph.types import Send
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState
from swarm.nodes.queen import queen_decompose_node, queen_fanout_router


def test_queen_decompose_returns_durable_state_delta():
    state = SwarmState(
        swarm_id="swarm-queen-test",
        objective="Build a small Flutter app",
        config=SwarmConfig(max_agents=2, topology="hierarchical"),
    ).to_json_dict()

    out = queen_decompose_node(state)

    assert out["iteration"] == 1
    assert out["status"] == "decomposing"
    assert len(out["agents"]) == 2
    assert len(out["tasks"]) == 2
    assert out["tasks"][0]["context"]["queen_directive"]["assigned_agent_id"]
    assert out["history"][-1]["kind"] == "task_assigned"


def test_queen_fanout_router_is_read_only():
    state = SwarmState(
        swarm_id="swarm-queen-router",
        objective="Build a small Flutter app",
        config=SwarmConfig(max_agents=2, topology="hierarchical"),
    ).to_json_dict()
    decomposed = queen_decompose_node(state)
    before = dict(decomposed)

    sends = queen_fanout_router(decomposed)

    assert isinstance(sends, list)
    assert len(sends) == 2
    assert all(isinstance(send, Send) for send in sends)
    assert decomposed == before


def test_queen_fanout_router_returns_end_without_directives():
    state = SwarmState(
        swarm_id="swarm-queen-empty",
        objective="Build a small Flutter app",
        config=SwarmConfig(max_agents=2, topology="hierarchical"),
    ).to_json_dict()

    assert queen_fanout_router(state) == "__end__"
