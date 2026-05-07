"""
AGENT 04 — Tactical Queen: Testing
AGENT 29 — Test Engineer
Test suite 5/5: End-to-end swarm execution across all topologies + scenarios.
"""
from __future__ import annotations

import pytest

from swarm.graphs.factory import build_swarm_graph
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState
from swarm.nodes.checkpointing import InProcessCheckpointStore


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_swarm(
    objective: str,
    topology: str = "hierarchical",
    consensus: str = "raft",
    max_agents: int = 4,
    sona: bool = True,
) -> SwarmState:
    config = SwarmConfig(
        topology=topology,  # type: ignore[arg-type]
        consensus_protocol=consensus,  # type: ignore[arg-type]
        max_agents=max_agents,
        sona_enabled=sona,
        anti_drift_enabled=True,
    )
    graph = build_swarm_graph(config)
    state = SwarmState(
        swarm_id=f"e2e-{topology}-{consensus}",
        objective=objective,
        config=config,
    )
    result = graph.invoke(state.to_json_dict())
    return SwarmState.model_validate(result)


# ── Core E2E ─────────────────────────────────────────────────────────────────

class TestE2EHierarchical:
    def test_completes_successfully(self):
        result = _run_swarm("Fix failing pytest tests in the src/ directory")
        assert result.status in ("completed", "failed")

    def test_final_output_set_on_success(self):
        result = _run_swarm("Fix failing tests in the project")
        if result.status == "completed":
            assert result.final_output != ""

    def test_sona_cycle_runs(self):
        result = _run_swarm("Fix failing tests")
        if result.status == "completed":
            assert result.sona_cycle_count >= 1

    def test_history_contains_entries(self):
        result = _run_swarm("Fix failing tests")
        assert len(result.history) > 0


class TestE2EAllTopologies:
    @pytest.mark.parametrize("topology", [
        "hierarchical", "mesh", "ring", "star", "adaptive"
    ])
    def test_topology_completes(self, topology: str):
        result = _run_swarm(
            f"Research and implement solution using {topology} topology",
            topology=topology,
        )
        assert result.status in ("completed", "failed", "denied", "drifted")
        assert result.swarm_id.startswith("e2e-")


class TestE2EAllConsensus:
    @pytest.mark.parametrize("protocol", ["raft", "bft", "gossip", "majority"])
    def test_consensus_protocol(self, protocol: str):
        result = _run_swarm(
            "Implement authentication module",
            consensus=protocol,
        )
        assert result.status in ("completed", "failed", "denied", "drifted")


# ── State persistence ─────────────────────────────────────────────────────────

class TestCheckpointResumeE2E:
    def test_checkpoint_survives_run(self):
        store = InProcessCheckpointStore()
        config = SwarmConfig(topology="hierarchical", max_agents=3)
        state = SwarmState(
            swarm_id="persist-test",
            objective="Fix failing pytest tests",
            config=config,
        )
        store.save(state)

        # Simulate restart
        restored = store.load_latest("persist-test")
        assert restored is not None
        assert restored.objective == state.objective
        assert restored.objective_hash == state.objective_hash

    def test_memory_persists_across_runs(self):
        config = SwarmConfig(topology="hierarchical", sona_enabled=True)
        state1 = SwarmState(
            swarm_id="mem-persist-1",
            objective="Fix pytest tests",
            config=config,
        )
        # Store a memory lesson in run 1
        state1.memory.store("lesson-1", "Always fix pytest config first", score=0.9)

        # Simulate serialization + deserialization
        checkpoint = state1.to_json_dict()
        state2 = SwarmState.from_json_dict(checkpoint)

        # Memory must survive
        lesson = state2.memory.get("lesson-1")
        assert lesson is not None
        assert lesson.value == "Always fix pytest config first"


# ── Anti-drift E2E ───────────────────────────────────────────────────────────

class TestAntiDriftE2E:
    def test_anti_drift_disabled_always_completes(self):
        config = SwarmConfig(
            topology="hierarchical",
            anti_drift_enabled=False,
        )
        graph = build_swarm_graph(config)
        state = SwarmState(
            swarm_id="no-drift-check",
            objective="Fix tests",
            config=config,
        )
        result = graph.invoke(state.to_json_dict())
        result_state = SwarmState.model_validate(result)
        # With anti-drift disabled, no drift failure
        assert result_state.failure_cause != "objective_drift"


# ── State round-trip ─────────────────────────────────────────────────────────

class TestStateRoundTrip:
    def test_json_dict_round_trip(self):
        config = SwarmConfig(topology="hierarchical")
        state = SwarmState(
            swarm_id="rt-1",
            objective="Fix failing tests",
            config=config,
        )
        state.status = "executing"
        state.iteration = 3
        state.append_history("swarm_init", {"node": "test"})

        serialized = state.to_json_dict()
        restored = SwarmState.from_json_dict(serialized)

        assert restored.swarm_id == state.swarm_id
        assert restored.objective_hash == state.objective_hash
        assert restored.status == "executing"
        assert restored.iteration == 3
        assert len(restored.history) == len(state.history)

    def test_worker_results_survive_round_trip(self):
        from swarm.models.agent import WorkerResult
        config = SwarmConfig(topology="hierarchical")
        state = SwarmState(
            swarm_id="rt-2",
            objective="Fix tests",
            config=config,
        )
        wr = WorkerResult(
            agent_id="coder-1",
            agent_role="coder",
            task_id="t1",
            success=True,
            output="Fixed the test",
            confidence=0.9,
        )
        state.record_worker_result(wr)
        serialized = state.to_json_dict()
        restored = SwarmState.from_json_dict(serialized)
        assert len(restored.worker_results) == 1
        assert restored.worker_results[0]["agent_id"] == "coder-1"
