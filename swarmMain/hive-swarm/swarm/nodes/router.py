"""
AGENT 14 — Router Node Specialist
3-Tier complexity routing: fast path → medium path → full swarm.
Ruflo: ADR-026 — Tier 1 (WASM/<1ms), Tier 2 (Haiku/~500ms), Tier 3 (Opus+Swarm).
"""
from __future__ import annotations

import re
from typing import Any

from ..models.state import SwarmState
from ..models.types import ComplexityTier, SwarmTopology


# ---------------------------------------------------------------------------
# Complexity scoring heuristics
# ---------------------------------------------------------------------------

_COMPLEX_KEYWORDS = frozenset([
    "architecture", "design", "security", "refactor", "optimize",
    "distributed", "concurrent", "async", "database", "schema",
    "authentication", "authorization", "encryption", "multi-agent",
    "orchestrat", "consensus", "fault-tolerant", "implement", "build",
    "create system", "entire", "comprehensive", "full",
])

_SIMPLE_KEYWORDS = frozenset([
    "rename", "typo", "format", "indent", "comment", "docstring",
    "add type hint", "add import", "fix lint", "const", "var",
])


def estimate_complexity(task_description: str) -> float:
    """
    Heuristic complexity score in [0, 1].
    Ruflo Tier 1: simple transforms (var→const, add types)  → score < 0.15
    Ruflo Tier 2: single LLM call (low complexity <30%)     → 0.15–0.50
    Ruflo Tier 3: swarm (complex reasoning, architecture)   → > 0.50
    """
    text = task_description.lower()
    word_count = len(text.split())

    # Simple keyword matches → low score
    simple_hits = sum(1 for kw in _SIMPLE_KEYWORDS if kw in text)
    # Complex keyword matches → high score
    complex_hits = sum(1 for kw in _COMPLEX_KEYWORDS if kw in text)

    # Base score from word count (longer = more complex)
    length_score = min(word_count / 200.0, 0.5)

    # Adjust for keywords
    keyword_score = (complex_hits * 0.12) - (simple_hits * 0.08)

    # Raw score in [0, 1]
    raw = max(0.0, min(1.0, length_score + keyword_score))
    return round(raw, 3)


# ---------------------------------------------------------------------------
# Topology-aware routing targets
# ---------------------------------------------------------------------------

_TOPOLOGY_QUEEN_NODE: dict[SwarmTopology, str] = {
    "hierarchical": "hierarchical_queen",
    "mesh":         "mesh_queen",
    "ring":         "ring_queen",
    "star":         "star_queen",
    "adaptive":     "adaptive_queen",
}


# ---------------------------------------------------------------------------
# Route function — used as conditional edge in LangGraph
# ---------------------------------------------------------------------------

def route_task(state: dict[str, Any]) -> str:
    """
    LangGraph conditional edge function.
    Returns the node name to route to based on complexity score + topology.

    Usage:
        builder.add_conditional_edges("route_task", route_task, {
            "fast_agent":          "fast_agent",
            "medium_agent":        "medium_agent",
            "hierarchical_queen":  "hierarchical_queen",
            "mesh_queen":          "mesh_queen",
            "ring_queen":          "ring_queen",
            "star_queen":          "star_queen",
            "adaptive_queen":      "adaptive_queen",
        })
    """
    swarm = SwarmState.model_validate(state)
    tier = swarm.config.complexity_tier(swarm.complexity_score)

    if tier == "tier1_fast":
        return "fast_agent"
    elif tier == "tier2_medium":
        return "medium_agent"
    else:
        topology = swarm.config.topology
        return _TOPOLOGY_QUEEN_NODE.get(topology, "hierarchical_queen")


# ---------------------------------------------------------------------------
# Router node — scores complexity and writes back into state
# ---------------------------------------------------------------------------

def router_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node function.
    Computes complexity score, sets complexity_tier, updates status.
    """
    swarm = SwarmState.model_validate(state)
    swarm.status = "routing"

    # Score the current objective (or current task description if set)
    target_text = swarm.objective
    if swarm.current_task_id:
        for t in swarm.tasks:
            if t.task_id == swarm.current_task_id:
                target_text = t.description
                break

    score = estimate_complexity(target_text)
    tier = swarm.config.complexity_tier(score)

    swarm.complexity_score = score
    swarm.complexity_tier = tier  # type: ignore[assignment]
    swarm.append_history("swarm_init", {
        "node": "router",
        "complexity_score": score,
        "tier": tier,
    })
    swarm.touch()
    return swarm.to_json_dict()
