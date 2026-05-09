"""Router node — patched.

F-14A: word-boundary regex (was substring match producing false positives like
       "build" matching every coding task)
F-14-OBS1: history kind = "route" (was misleading "swarm_init")
F-14-CORR3: length denominator widened so tier 1/2 are reachable
"""

from __future__ import annotations

import re
from typing import Any

from ..models.state import SwarmState
from ..models.types import QUEEN_NODE_NAMES, SwarmTopology

# ── Word-boundary regex patterns (F-14A) ──────────────────────────────────

_COMPLEX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(architecture|architect)\b", re.IGNORECASE),
    re.compile(r"\bdesign\b", re.IGNORECASE),
    re.compile(r"\b(security|secure)\b", re.IGNORECASE),
    re.compile(r"\brefactor(?:ing)?\b", re.IGNORECASE),
    re.compile(r"\boptimi[sz]e?\b", re.IGNORECASE),
    re.compile(r"\bdistributed\b", re.IGNORECASE),
    re.compile(r"\bconcurren(?:t|cy)\b", re.IGNORECASE),
    re.compile(r"\basync(?:hronous)?\b", re.IGNORECASE),
    re.compile(r"\bdatabase\b", re.IGNORECASE),
    re.compile(r"\bschema\b", re.IGNORECASE),
    re.compile(r"\b(authentication|authorization)\b", re.IGNORECASE),
    re.compile(r"\bencrypt(?:ion)?\b", re.IGNORECASE),
    re.compile(r"\bmulti[- ]agent\b", re.IGNORECASE),
    re.compile(r"\borchestrat(?:e|ion|or)\b", re.IGNORECASE),
    re.compile(r"\bconsensus\b", re.IGNORECASE),
    re.compile(r"\bfault[- ]tolerant\b", re.IGNORECASE),
    re.compile(r"\b(comprehensive|entire|full[- ]system)\b", re.IGNORECASE),
]

_SIMPLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brename\b", re.IGNORECASE),
    re.compile(r"\btypo\b", re.IGNORECASE),
    re.compile(r"\bformat\b", re.IGNORECASE),
    re.compile(r"\b(indent|indentation)\b", re.IGNORECASE),
    re.compile(r"\bcomment\b", re.IGNORECASE),
    re.compile(r"\bdocstring\b", re.IGNORECASE),
    re.compile(r"\badd type hint\b", re.IGNORECASE),
    re.compile(r"\badd import\b", re.IGNORECASE),
    re.compile(r"\bfix lint\b", re.IGNORECASE),
]


def estimate_complexity(task_description: str) -> float:
    """Heuristic complexity score in [0, 1]. F-14A/CORR3."""
    if not task_description:
        return 0.0
    text = task_description
    word_count = len(text.split())

    simple_hits = sum(1 for p in _SIMPLE_PATTERNS if p.search(text))
    complex_hits = sum(1 for p in _COMPLEX_PATTERNS if p.search(text))

    # F-14-CORR3: widen denominator so short complex tasks don't always hit tier 3
    length_score = min(word_count / 400.0, 0.4)
    keyword_score = (complex_hits * 0.13) - (simple_hits * 0.10)

    raw = max(0.0, min(1.0, length_score + keyword_score))
    return round(raw, 3)


def route_task(state: dict[str, Any]) -> str:
    """LangGraph conditional edge function."""
    swarm = SwarmState.model_validate(state)
    tier = swarm.config.complexity_tier(swarm.complexity_score)

    if tier == "tier1_fast":
        return "fast_agent"
    if tier == "tier2_medium":
        return "medium_agent"

    topology: SwarmTopology = swarm.config.topology
    return QUEEN_NODE_NAMES.get(topology, "hierarchical_queen")


def router_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: compute complexity + tier, write back into state."""
    swarm = SwarmState.model_validate(state)
    swarm.status = "routing"

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
    # F-14-OBS1: distinct history kind
    swarm.append_history(
        "route",
        {
            "node": "router",
            "complexity_score": score,
            "tier": tier,
        },
    )
    swarm.touch()
    return swarm.to_json_dict()


__all__ = ["estimate_complexity", "route_task", "router_node"]
