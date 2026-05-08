from swarm import SwarmConfig, SwarmState
from swarm.nodes import queen as queen_module
from swarm.nodes.scaling import scaling_node


class _VMem:
    available = 768 * 1024 * 1024


class _Psutil:
    @staticmethod
    def virtual_memory():
        return _VMem()


def _state(config: SwarmConfig | None = None) -> SwarmState:
    return SwarmState(
        swarm_id="s1",
        objective="Build a tested API service",
        config=config or SwarmConfig(),
        complexity_tier="tier3_swarm",
    )


def test_scaling_node_noop_when_disabled():
    state = _state()

    out = scaling_node(state.to_json_dict())

    assert out["runtime_metadata"] == {}


def test_scaling_node_records_runtime_cap(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "psutil", _Psutil)
    state = _state(SwarmConfig(auto_scale_agents=True, max_agents=5, scaling_ram_per_agent_mb=512))

    out = scaling_node(state.to_json_dict())

    assert out["runtime_metadata"]["applied_agent_cap"] == 1
    assert out["config"]["max_agents"] == 5


def test_queen_consumes_runtime_cap(monkeypatch):
    monkeypatch.setattr(queen_module, "_HAS_SEND", False)
    state = _state(SwarmConfig(max_agents=5))
    state.runtime_metadata["applied_agent_cap"] = 2

    out = queen_module.queen_node(state.to_json_dict())[0]

    assert len(out["tasks"]) == 2
    assert len(out["agents"]) == 2
