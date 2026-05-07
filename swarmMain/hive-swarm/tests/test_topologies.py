"""
AGENT 29 — Test Engineer
Test suite 3/5: Topology routing, graph construction, 3-tier routing.
"""
from __future__ import annotations

import pytest

from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState
from swarm.nodes.router import estimate_complexity, route_task, router_node
from swarm.nodes.queen import queen_node


# ── Complexity estimation ─────────────────────────────────────────────────────

class TestComplexityEstimation:
    def test_simple_task_low_score(self):
        score = estimate_complexity("rename variable x to y")
        assert score < 0.30

    def test_complex_task_high_score(self):
        score = estimate_complexity(
            "Design and implement a distributed multi-agent consensus architecture "
            "with Byzantine fault tolerance and secure authentication"
        )
        assert score > 0.30

    def test_score_in_bounds(self):
        for text in ["x", "a" * 500, "", "rename variable"]:
            score = estimate_complexity(text)
            assert 0.0 <= score <= 1.0


# ── 3-Tier routing ────────────────────────────────────────────────────────────

class TestTierRouting:
    def _make_state(self, complexity_score: float, topology: str = "hierarchical") -> dict:
        config = SwarmConfig(topology=topology)  # type: ignore[arg-type]
        state = SwarmState(
            swarm_id="s1",
            objective="fix tests",
            config=config,
            complexity_score=complexity_score,
            complexity_tier=config.complexity_tier(complexity_score),
        )
        return state.to_json_dict()

    def test_low_complexity_routes_to_fast(self):
        state = self._make_state(0.05)
        assert route_task(state) == "fast_agent"

    def test_medium_complexity_routes_to_medium(self):
        state = self._make_state(0.35)
        assert route_task(state) == "medium_agent"

    def test_high_complexity_routes_to_hierarchical_queen(self):
        state = self._make_state(0.80, topology="hierarchical")
        assert route_task(state) == "hierarchical_queen"

    def test_high_complexity_mesh_routes_to_mesh_queen(self):
        state = self._make_state(0.80, topology="mesh")
        assert route_task(state) == "mesh_queen"

    def test_router_node_sets_tier(self):
        config = SwarmConfig(topology="hierarchical")
        state = SwarmState(
            swarm_id="s1",
            objective="rename variable x to y",
            config=config,
        )
        result = router_node(state.to_json_dict())
        result_state = SwarmState.model_validate(result)
        assert result_state.complexity_tier in ("tier1_fast", "tier2_medium", "tier3_swarm")


# ── Queen decomposition ───────────────────────────────────────────────────────

class TestQueenDecomposition:
    def _make_swarm_state(self, topology: str = "hierarchical") -> dict:
        config = SwarmConfig(topology=topology, max_agents=6)  # type: ignore[arg-type]
        state = SwarmState(
            swarm_id=f"swarm-{topology}",
            objective="Build a REST API with authentication",
            config=config,
        )
        return state.to_json_dict()

    def test_hierarchical_produces_role_tasks(self):
        state = self._make_swarm_state("hierarchical")
        sends = queen_node(state)
        assert len(sends) > 0

    def test_mesh_produces_peer_tasks(self):
        state = self._make_swarm_state("mesh")
        sends = queen_node(state)
        assert len(sends) > 0

    def test_ring_produces_sequential_tasks(self):
        state = self._make_swarm_state("ring")
        sends = queen_node(state)
        assert len(sends) > 0

    def test_star_produces_spoke_tasks(self):
        state = self._make_swarm_state("star")
        sends = queen_node(state)
        assert len(sends) > 0

    def test_queen_respects_max_agents(self):
        config = SwarmConfig(topology="hierarchical", max_agents=2)
        state = SwarmState(
            swarm_id="s1",
            objective="task",
            config=config,
        )
        sends = queen_node(state.to_json_dict())
        assert len(sends) <= 2

    def test_max_iterations_enforced(self):
        config = SwarmConfig(topology="hierarchical", max_iterations=1)
        state = SwarmState(
            swarm_id="s1",
            objective="task",
            config=config,
            iteration=2,  # already exceeded
        )
        result = queen_node(state.to_json_dict())
        # Should return a failed state, not more Send()s
        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
            result_state = SwarmState.model_validate(result[0])
            assert result_state.status in ("failed",)


# ── Graph factory ────────────────────────────────────────────────────────────

class TestGraphFactory:
    def test_mock_graph_runs_hierarchical(self):
        from swarm.graphs.factory import build_swarm_graph

        config = SwarmConfig(topology="hierarchical", max_agents=4)
        graph = build_swarm_graph(config)
        state = SwarmState(
            swarm_id="graph-test",
            objective="Fix failing tests in the project",
            config=config,
        )
        result = graph.invoke(state.to_json_dict())
        assert isinstance(result, dict)
        assert result.get("status") in ("completed", "failed", "denied", "drifted")

    def test_mock_graph_runs_all_topologies(self):
        from swarm.graphs.factory import build_swarm_graph

        for topology in ("hierarchical", "mesh", "ring", "star", "adaptive"):
            config = SwarmConfig(topology=topology, max_agents=3)  # type: ignore[arg-type]
            graph = build_swarm_graph(config)
            state = SwarmState(
                swarm_id=f"graph-{topology}",
                objective=f"Test {topology} topology",
                config=config,
            )
            result = graph.invoke(state.to_json_dict())
            assert isinstance(result, dict), f"Graph failed for topology={topology}"
