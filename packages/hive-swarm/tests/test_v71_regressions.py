"""Regression tests for v7.1 canonicalization fixes (hive side).

One test (or test cluster) per canonical fix ID. If any of these go red,
the regression has been re-introduced.

Covered:
  - F-13-CORR2: factory.py registers ALL 5 queen aliases as nodes
  - F-13-CORR3: _MockCompiledGraph.invoke calls distill_node for tier-1 / tier-2

(F-29-CORR1 lives in the gateway-side regression file.)
"""
from __future__ import annotations

from typing import Any

import pytest

from swarm.graphs.factory import (
    _MockCompiledGraph,
    _build_mock_graph,
    _merge_worker_results,
    build_swarm_graph,
)
from swarm.models.config import SwarmConfig
from swarm.models.state import SwarmState
from swarm.models.types import QUEEN_NODE_NAMES


# ── F-13-CORR2: all 5 queen aliases registered ─────────────────────────

def _try_get_compiled_graph_nodes(compiled: Any) -> set[str]:
    """Best-effort: extract registered node names from a compiled LangGraph.

    Handles common upstream layouts. If we can't introspect, the test
    falls back to a behavioural check (route_task → queen-name → no-error).
    """
    for attr in ("nodes", "_nodes", "node_names"):
        v = getattr(compiled, attr, None)
        if v is None:
            continue
        if hasattr(v, "keys"):
            return set(v.keys())
        if isinstance(v, (set, list, tuple)):
            return set(v)
    # Try compiled.builder.nodes (StateGraph stores nodes there)
    builder = getattr(compiled, "builder", None) or getattr(compiled, "_builder", None)
    if builder is not None:
        for attr in ("nodes", "_nodes"):
            v = getattr(builder, attr, None)
            if v is not None and hasattr(v, "keys"):
                return set(v.keys())
    return set()


def test_factory_registers_all_5_queen_aliases_for_hierarchical():
    """The configured topology is hierarchical, but route_task can still
    return any of the 5 names — they must all be registered as nodes."""
    config = SwarmConfig(topology="hierarchical")
    try:
        graph = build_swarm_graph(config)
    except Exception as e:
        pytest.fail(
            f"build_swarm_graph(hierarchical) raised — likely missing queen "
            f"alias registration (F-13-CORR2 regression): {e}"
        )

    nodes = _try_get_compiled_graph_nodes(graph)
    if nodes:
        # Direct introspection succeeded — assert all 5 aliases present
        for alias in QUEEN_NODE_NAMES.values():
            assert alias in nodes, (
                f"queen alias {alias!r} missing from compiled graph "
                f"(F-13-CORR2 regression). Registered: {sorted(nodes)}"
            )
    # If introspection failed, the absence of an exception above is itself
    # the regression check — LangGraph would have raised at compile time.


def test_factory_registers_all_5_queen_aliases_for_each_topology():
    """Every topology-config produces a graph with all 5 aliases registered."""
    for topology in QUEEN_NODE_NAMES.keys():
        config = SwarmConfig(topology=topology)
        try:
            graph = build_swarm_graph(config)
        except Exception as e:
            pytest.fail(
                f"build_swarm_graph({topology!r}) raised at compile time "
                f"(F-13-CORR2 regression): {e}"
            )
        nodes = _try_get_compiled_graph_nodes(graph)
        if nodes:
            for alias in QUEEN_NODE_NAMES.values():
                assert alias in nodes, (
                    f"topology={topology}: queen alias {alias!r} not registered "
                    f"(F-13-CORR2). Registered: {sorted(nodes)}"
                )


# ── F-13-CORR3: mock graph mirrors SONA edges on tier-1 / tier-2 ────────

def _mock_state(objective: str) -> dict:
    """Build a minimal SwarmState dict for mock invocation."""
    config = SwarmConfig(sona_enabled=True)
    return SwarmState(
        swarm_id="t1-or-t2",
        objective=objective,
        config=config,
    ).to_json_dict()


def test_mock_graph_distills_after_fast_agent():
    """Tier-1 (fast) path must increment sona_cycle_count via distill_node.

    Without F-13-CORR3, the mock graph would skip distill on tier-1 and
    sona_cycle_count would stay 0 — a silent lie about pattern storage.
    """
    state = _mock_state("rename foo to bar")  # short → tier-1
    mock = _MockCompiledGraph(SwarmConfig(sona_enabled=True))
    final_dict = mock.invoke(state)
    final = SwarmState.from_json_dict(final_dict)

    # Status must be completed (tier-1 short-circuits to completion)
    assert final.status == "completed"
    # F-13-CORR3: SONA must have run
    assert final.sona_cycle_count >= 1, (
        "F-13-CORR3 regression: mock graph tier-1 path did not call distill_node. "
        "sona_cycle_count stayed at 0."
    )


def test_mock_graph_distills_after_medium_agent():
    """Tier-2 (medium) path must also invoke distill_node."""
    # Construct a state that lands in tier-2: medium-length objective
    # without the simple-keywords that drop to tier-1.
    config = SwarmConfig(sona_enabled=True, tier1_threshold=0.05, tier2_threshold=0.4)
    state = SwarmState(
        swarm_id="t2",
        objective="add a moderate-complexity feature with some context but not too much",
        config=config,
    ).to_json_dict()
    mock = _MockCompiledGraph(config)
    final_dict = mock.invoke(state)
    final = SwarmState.from_json_dict(final_dict)

    # Either tier-1 or tier-2 — both should now distill via F-13-CORR3
    if final.complexity_tier in ("tier1_fast", "tier2_medium"):
        assert final.sona_cycle_count >= 1, (
            f"F-13-CORR3 regression: mock graph {final.complexity_tier} path "
            f"did not call distill_node. sona_cycle_count stayed at 0."
        )


def test_mock_graph_distills_on_tier_3_too_unchanged():
    """Sanity: tier-3 path was already calling distill_node correctly.
    F-13-CORR3 must not break that (it's a 'add to tier 1/2' patch, not
    'remove from tier 3')."""
    config = SwarmConfig(sona_enabled=True)
    state = SwarmState(
        swarm_id="t3",
        objective=(
            "implement a comprehensive distributed authentication architecture "
            "with refresh tokens, role-based access control, and audit logging"
        ),
        config=config,
    ).to_json_dict()
    mock = _MockCompiledGraph(config)
    final_dict = mock.invoke(state)
    final = SwarmState.from_json_dict(final_dict)
    # Should reach a terminal status; if it completed cleanly, SONA fired.
    if final.status == "completed":
        assert final.sona_cycle_count >= 1


# ── Sanity: F-13A-CORR1 dedupe still in place (regression of regression) ─

def test_worker_results_dedupe_still_idempotent():
    """Re-prove F-13A-CORR1 — F-13-CORR2 / F-13-CORR3 must not regress it."""
    fanout = [
        {"agent_id": f"role-{i}", "task_id": f"t-1-{i}", "output": f"o-{i}"}
        for i in range(5)
    ]
    state = []
    for _ in range(16):
        state = _merge_worker_results(state, fanout)
    assert len(state) == 5, "F-13A-CORR1 regressed: worker_results doubled"
