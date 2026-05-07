"""
AGENT 13 — LangGraph Graph Builder Specialist
AGENT 25 — Topology Specialist

build_swarm_graph() factory + all 5 topology-specific builders.
Full StateGraph construction with nodes, edges, conditional edges, checkpointer.
"""
from __future__ import annotations

from typing import Any

from ..models.config import SwarmConfig
from ..models.state import SwarmState
from ..nodes.approval import approval_node, route_after_approval
from ..nodes.checkpointing import SwarmRedactingCheckpointer
from ..nodes.consensus import consensus_node, route_after_consensus
from ..nodes.judge import judge_node, route_after_judge
from ..nodes.queen import fast_agent_node, medium_agent_node, queen_node
from ..nodes.router import route_task, router_node
from ..nodes.sona import distill_node, memory_retrieve_node
from ..nodes.worker import collect_results_node, worker_node

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.checkpoint.memory import InMemorySaver
    _HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover
    _HAS_LANGGRAPH = False
    StateGraph = None      # type: ignore[assignment,misc]
    END = "__end__"
    START = "__start__"
    InMemorySaver = None   # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Topology routing targets
# ---------------------------------------------------------------------------

_QUEEN_NODE_NAMES = {
    "hierarchical": "hierarchical_queen",
    "mesh":         "mesh_queen",
    "ring":         "ring_queen",
    "star":         "star_queen",
    "adaptive":     "adaptive_queen",
}


# ---------------------------------------------------------------------------
# Main factory (Agent 25 consensus: Raft — architectural decision)
# ---------------------------------------------------------------------------

def build_swarm_graph(
    config: SwarmConfig,
    checkpointer: Any | None = None,
) -> Any:
    """
    Build the correct LangGraph StateGraph for the given SwarmConfig.

    Architecture (Raft consensus decision — Agent 02):
      All topologies share the same node set.
      Only the queen_node decomposition strategy varies by topology.
      Conditional edges handle routing, approval, retry, and SONA.

    Returns a compiled LangGraph graph (or dict-based mock if LangGraph unavailable).
    """
    if not _HAS_LANGGRAPH or StateGraph is None:
        return _build_mock_graph(config)

    builder = StateGraph(dict)   # state is dict (SwarmState.to_json_dict())

    # ── Nodes ─────────────────────────────────────────────────────────────────

    queen_name = _QUEEN_NODE_NAMES[config.topology]

    builder.add_node("memory_retrieve",    memory_retrieve_node)
    builder.add_node("route_task",         router_node)
    builder.add_node("fast_agent",         fast_agent_node)
    builder.add_node("medium_agent",       medium_agent_node)
    builder.add_node(queen_name,           queen_node)
    builder.add_node("worker_node",        worker_node)
    builder.add_node("collect_results",    collect_results_node)
    builder.add_node("consensus_node",     consensus_node)
    builder.add_node("approval_node",      approval_node)
    builder.add_node("judge_node",         judge_node)
    builder.add_node("distill_node",       distill_node)

    # ── Entry ──────────────────────────────────────────────────────────────────
    builder.add_edge(START, "memory_retrieve")
    builder.add_edge("memory_retrieve", "route_task")

    # ── 3-Tier routing (Agent 14) ──────────────────────────────────────────────
    all_queen_names = list(_QUEEN_NODE_NAMES.values())
    routing_targets = {
        "fast_agent":   "fast_agent",
        "medium_agent": "medium_agent",
        **{name: name for name in all_queen_names},
    }
    builder.add_conditional_edges("route_task", route_task, routing_targets)

    # ── Tier 1 / Tier 2 → distill → END ───────────────────────────────────────
    builder.add_edge("fast_agent",   "distill_node")
    builder.add_edge("medium_agent", "distill_node")

    # ── Tier 3: Queen → workers (Send() fan-out) → collect → consensus ────────
    for name in all_queen_names:
        builder.add_edge(name, "collect_results")    # fan-in after Send()
    builder.add_edge("collect_results", "consensus_node")

    # ── After consensus: route to approval or judge ────────────────────────────
    builder.add_conditional_edges(
        "consensus_node",
        route_after_consensus,
        {"approval_node": "approval_node", "judge_node": "judge_node", "end": END},
    )

    # ── After approval: judge or end ───────────────────────────────────────────
    builder.add_conditional_edges(
        "approval_node",
        route_after_approval,
        {"judge_node": "judge_node", "end": END},
    )

    # ── After judge: distill or retry or end ──────────────────────────────────
    builder.add_conditional_edges(
        "judge_node",
        route_after_judge,
        {"distill_node": "distill_node", "route_task": "route_task", "end": END},
    )

    # ── Distill → END ─────────────────────────────────────────────────────────
    builder.add_edge("distill_node", END)

    # ── Compile with checkpointer ─────────────────────────────────────────────
    cp = checkpointer
    if cp is None:
        raw_cp = InMemorySaver()
        cp = SwarmRedactingCheckpointer(raw_cp)

    return builder.compile(checkpointer=cp)


# ---------------------------------------------------------------------------
# Mock graph for environments without LangGraph (test / CI without deps)
# ---------------------------------------------------------------------------

class _MockCompiledGraph:
    """Minimal LangGraph-compatible stub for offline testing."""

    def __init__(self, config: SwarmConfig) -> None:
        self.config = config

    def invoke(self, state: dict[str, Any], config: dict | None = None) -> dict[str, Any]:
        """Run the swarm pipeline synchronously using plain function calls."""
        # RETRIEVE
        state = memory_retrieve_node(state)
        # ROUTE
        state = router_node(state)
        tier = state.get("complexity_tier", "tier3_swarm")

        if tier == "tier1_fast":
            state = fast_agent_node(state)
        elif tier == "tier2_medium":
            state = medium_agent_node(state)
        else:
            # Queen decompose + collect (sequential for mock)
            sends = queen_node(state)
            worker_outputs = []
            for send in sends:
                payload = send[1] if isinstance(send, (list, tuple)) else send
                if isinstance(payload, dict):
                    result = worker_node(payload)
                    worker_results = state.get("worker_results", [])
                    wr = result.get("_worker_result")
                    if wr:
                        worker_results.append(wr)
                    state["worker_results"] = worker_results

            state = collect_results_node(state)
            state = consensus_node(state)
            swarm_status = state.get("status", "")
            if swarm_status == "awaiting_approval":
                state = approval_node(state)
            if state.get("status") not in ("failed", "denied"):
                state = judge_node(state)
            if state.get("status") not in ("failed", "denied"):
                state = distill_node(state)

        return state

    def get_state(self, config: dict) -> Any:
        return None


def _build_mock_graph(config: SwarmConfig) -> _MockCompiledGraph:
    return _MockCompiledGraph(config)
