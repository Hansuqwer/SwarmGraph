"""Graph factory — patched (v7).

History:
  F-13A (v4): registers `worker_results` reducer for parallel Send fan-out.
  F-13B (v4): recursion_limit derived from config.max_iterations.
  F-13C (v4): queen_node names sourced from models.types.QUEEN_NODE_NAMES.
  F-13-LG2 (v4): mock graph accepts approve/deny override.
  F-15-LG4 (your local fix): queen Send fan-out as conditional edge.
  v7 — F-13A-CORR1 (CRITICAL): replace `operator.add` reducer with a
       dedupe-merge reducer keyed on (agent_id, task_id). Fixes the
       80-vs-5 bug where LangGraph re-emits state during retry loops,
       causing operator.add to concatenate the same WorkerResult dicts
       repeatedly. With dedupe-merge, re-invocations are idempotent.

Why dedupe is correct semantically:
  Each worker is unique by (agent_id, task_id). Two `WorkerResult`s with
  the same key in the same `worker_results` list never represent two
  distinct calls — they always represent state replay. Merging by key
  preserves the latest values (LATER wins on key collision).
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from ..models.config import SwarmConfig
from ..models.types import QUEEN_NODE_NAMES
from ..nodes.approval import approval_node, route_after_approval
from ..nodes.checkpointing import SwarmRedactingCheckpointer
from ..nodes.consensus import consensus_node, route_after_consensus
from ..nodes.judge import judge_node, route_after_judge
from ..nodes.queen import fast_agent_node, medium_agent_node, queen_node
from ..nodes.router import route_task, router_node
from ..nodes.scaling import scaling_node
from ..nodes.sona import distill_node, memory_retrieve_node
from ..nodes.worker import collect_results_node, worker_node

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

    _HAS_LANGGRAPH = True
except ImportError:  # pragma: no cover
    _HAS_LANGGRAPH = False
    StateGraph = None  # type: ignore[assignment,misc]
    END = "__end__"
    START = "__start__"
    InMemorySaver = None  # type: ignore[assignment]


# ── F-13A-CORR1: dedupe-merge reducer for worker_results ─────────────────


def _merge_worker_results(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Idempotent merge of worker results.

    Key: (agent_id, task_id). Right wins on collision (LATER state replaces
    earlier). Preserves order: existing-then-new for new keys, old position
    for replaced keys.

    Why this matters: LangGraph's `operator.add` on lists is concatenation.
    During retry loops or checkpoint replay, the same WorkerResult dict
    appears in subsequent re-invocations. operator.add appends them again,
    inflating worker_count by N×iterations. dedupe by (agent_id, task_id)
    makes the reducer idempotent — re-emitting the same result is a no-op.

    Defensive: tolerates malformed dicts (missing agent_id/task_id) by
    keying on json-stable repr as a fallback.
    """
    if not left:
        return list(right or [])
    if not right:
        return list(left)

    def _key(r: dict[str, Any]) -> tuple[str, str]:
        if not isinstance(r, dict):
            return (repr(r), "")
        agent = str(r.get("agent_id", ""))
        task = str(r.get("task_id", ""))
        if not agent and not task:
            # Fallback for malformed entries: hash-stable repr
            return (repr(sorted(r.items())), "")
        return (agent, task)

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []

    for r in left:
        k = _key(r)
        if k not in merged:
            order.append(k)
        merged[k] = r

    for r in right:
        k = _key(r)
        if k not in merged:
            order.append(k)
        # right always wins on collision
        merged[k] = r

    return [merged[k] for k in order]


# ── State schema (v4 + F-13A-CORR1) ──────────────────────────────────────


class _SwarmGraphState(TypedDict, total=False):
    """LangGraph state schema with explicit reducers.

    F-13A-CORR1: worker_results uses dedupe-merge instead of operator.add.
    """

    worker_results: Annotated[list[dict[str, Any]], _merge_worker_results]
    swarm_id: str
    objective: str
    objective_hash: str
    schema_version: int
    config: dict[str, Any]
    agents: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    current_task_id: str | None
    completed_task_ids: list[str]
    complexity_score: float
    complexity_tier: str
    pending_votes: list[dict[str, Any]]
    consensus_result: dict[str, Any] | None
    consensus_round_id: str
    latest_output: str
    latest_output_hash: str
    final_output: str
    memory: dict[str, Any]
    sona_distilled: bool
    sona_cycle_count: int
    retrieved_context: list[dict[str, Any]]
    status: str
    failure_cause: str | None
    iteration: int
    approval_consumed: bool
    approval_decision_token: str
    history: list[dict[str, Any]]
    errors: list[str]
    created_at: float
    updated_at: float


# ── Main factory (unchanged contract) ────────────────────────────────────


def _queen_passthrough(state: dict[str, Any]) -> dict[str, Any]:
    """Queen fan-out is emitted by conditional edges, not node updates."""
    return state


def build_swarm_graph(
    config: SwarmConfig,
    checkpointer: Any | None = None,
) -> Any:
    """Build the LangGraph StateGraph for the given SwarmConfig."""
    if not _HAS_LANGGRAPH or StateGraph is None:
        return _build_mock_graph(config)

    builder = StateGraph(_SwarmGraphState)

    all_queen_names = list(QUEEN_NODE_NAMES.values())

    builder.add_node("memory_retrieve", memory_retrieve_node)
    builder.add_node("scaling_node", scaling_node)
    builder.add_node("route_task", router_node)
    builder.add_node("fast_agent", fast_agent_node)
    builder.add_node("medium_agent", medium_agent_node)
    for queen_name in all_queen_names:
        builder.add_node(queen_name, _queen_passthrough)
    builder.add_node("worker_node", worker_node)
    builder.add_node("collect_results", collect_results_node)
    builder.add_node("consensus_node", consensus_node)
    builder.add_node("approval_node", approval_node)
    builder.add_node("judge_node", judge_node)
    builder.add_node("distill_node", distill_node)

    builder.add_edge(START, "memory_retrieve")
    builder.add_edge("memory_retrieve", "scaling_node")
    builder.add_edge("scaling_node", "route_task")

    routing_targets = {
        "fast_agent": "fast_agent",
        "medium_agent": "medium_agent",
        **{name: name for name in all_queen_names},
    }
    builder.add_conditional_edges("route_task", route_task, routing_targets)

    builder.add_edge("fast_agent", "distill_node")
    builder.add_edge("medium_agent", "distill_node")

    for name in all_queen_names:
        builder.add_conditional_edges(name, queen_node, ["worker_node"])
    builder.add_edge("worker_node", "collect_results")
    builder.add_edge("collect_results", "consensus_node")

    builder.add_conditional_edges(
        "consensus_node",
        route_after_consensus,
        {"approval_node": "approval_node", "judge_node": "judge_node", "end": END},
    )
    builder.add_conditional_edges(
        "approval_node",
        route_after_approval,
        {"judge_node": "judge_node", "end": END},
    )
    builder.add_conditional_edges(
        "judge_node",
        route_after_judge,
        {"distill_node": "distill_node", "route_task": "route_task", "end": END},
    )

    builder.add_edge("distill_node", END)

    cp = checkpointer
    if cp is None:
        raw_cp = InMemorySaver()
        cp = SwarmRedactingCheckpointer(raw_cp)

    recursion_limit = max(25, config.max_iterations * 8)

    return builder.compile(checkpointer=cp).with_config({"recursion_limit": recursion_limit})


# ── Mock graph (uses the same dedupe reducer for parity) ─────────────────


class _MockCompiledGraph:
    def __init__(
        self,
        config: SwarmConfig,
        *,
        mock_approval_decision: str = "approve",
    ) -> None:
        self.config = config
        self.mock_approval_decision = mock_approval_decision

    def invoke(self, state, config=None):
        state = memory_retrieve_node(state)
        state = scaling_node(state)
        state = router_node(state)
        tier = state.get("complexity_tier", "tier3_swarm")

        if tier == "tier1_fast":
            state = fast_agent_node(state)
            state = distill_node(state)
        elif tier == "tier2_medium":
            state = medium_agent_node(state)
            state = distill_node(state)
        else:
            sends = queen_node(state)
            for send in sends:
                payload = send[1] if isinstance(send, (list, tuple)) else send
                if isinstance(payload, dict) and "agent_id" in payload:
                    result = worker_node(payload)
                    # F-13A-CORR1 also applied to mock for parity
                    existing = state.get("worker_results", [])
                    merged = _merge_worker_results(existing, result.get("worker_results", []))
                    state["worker_results"] = merged

            state = collect_results_node(state)
            state = consensus_node(state)
            if state.get("status") == "awaiting_approval":
                state = approval_node(state)
            if state.get("status") not in ("failed", "denied"):
                state = judge_node(state)
            if state.get("status") not in ("failed", "denied", "drifted"):
                state = distill_node(state)

        return state

    def get_state(self, config):
        return None


def _build_mock_graph(config: SwarmConfig) -> _MockCompiledGraph:
    return _MockCompiledGraph(config)


__all__ = ["build_swarm_graph", "_MockCompiledGraph", "_merge_worker_results"]
