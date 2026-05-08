"""
AGENT 16 — Graph Builder Specialist
LangGraph workflow: intake → classify → filter → quota → swarm → consensus → call → validate → update → END
"""
from __future__ import annotations

from typing import Any

from .nodes import (
    classify_request_node,
    consensus_node,
    intake_node,
    provider_call_node,
    provider_filter_node,
    quota_check_node,
    response_validation_node,
    swarm_route_node,
    usage_update_node,
)

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.checkpoint.memory import InMemorySaver
    _HAS_LANGGRAPH = True
except ImportError:
    _HAS_LANGGRAPH = False
    END = "__end__"
    START = "__start__"
    StateGraph = None
    InMemorySaver = None


def _route_after_intake(state: dict[str, Any]) -> str:
    from ..models.state import GatewayState
    s = GatewayState.from_json_dict(state)
    return "classify_request" if s.is_safe_to_proceed else END


def _route_after_quota(state: dict[str, Any]) -> str:
    from ..models.state import GatewayState
    s = GatewayState.from_json_dict(state)
    if not s.candidate_providers:
        return END   # No candidates — end gracefully
    return "swarm_route"


def _route_after_consensus(state: dict[str, Any]) -> str:
    from ..models.state import GatewayState
    s = GatewayState.from_json_dict(state)
    if not s.routing_decision or not s.routing_decision.selected_provider_id:
        return END
    return "provider_call"


def build_gateway_graph(checkpointer: Any = None) -> Any:
    """Build and compile the LangGraph gateway workflow."""
    if not _HAS_LANGGRAPH or StateGraph is None:
        return _MockGraph()

    builder = StateGraph(dict)

    # Add all nodes
    builder.add_node("intake",             intake_node)
    builder.add_node("classify_request",   classify_request_node)
    builder.add_node("provider_filter",    provider_filter_node)
    builder.add_node("quota_check",        quota_check_node)
    builder.add_node("swarm_route",        swarm_route_node)
    builder.add_node("consensus",          consensus_node)
    builder.add_node("provider_call",      provider_call_node)
    builder.add_node("response_validation",response_validation_node)
    builder.add_node("usage_update",       usage_update_node)

    # Entry
    builder.add_edge(START, "intake")

    # Conditional after intake: proceed or end
    builder.add_conditional_edges("intake", _route_after_intake, {
        "classify_request": "classify_request",
        END: END,
    })

    # Linear pipeline
    builder.add_edge("classify_request", "provider_filter")
    builder.add_edge("provider_filter",  "quota_check")

    # Conditional after quota: candidates exist or end
    builder.add_conditional_edges("quota_check", _route_after_quota, {
        "swarm_route": "swarm_route",
        END: END,
    })

    builder.add_edge("swarm_route", "consensus")

    # Conditional after consensus: provider selected or end
    builder.add_conditional_edges("consensus", _route_after_consensus, {
        "provider_call": "provider_call",
        END: END,
    })

    builder.add_edge("provider_call",       "response_validation")
    builder.add_edge("response_validation", "usage_update")
    builder.add_edge("usage_update",        END)

    cp = checkpointer or (InMemorySaver() if InMemorySaver else None)
    return builder.compile(checkpointer=cp)


class _MockGraph:
    """Sequential pipeline for environments without LangGraph installed."""
    def invoke(self, state: dict[str, Any], config: dict | None = None) -> dict[str, Any]:
        from ..models.state import GatewayState
        for node_fn in [
            intake_node, classify_request_node, provider_filter_node,
            quota_check_node, swarm_route_node, consensus_node,
            provider_call_node, response_validation_node, usage_update_node,
        ]:
            state = node_fn(state)
            s = GatewayState.from_json_dict(state)
            if not s.is_safe_to_proceed and node_fn.__name__ == "intake_node":
                break
        return state
