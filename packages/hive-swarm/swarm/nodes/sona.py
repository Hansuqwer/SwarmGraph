"""SONA loop — patched.

F-27A (HIGH): retrieved patterns are written to swarm.retrieved_context so
   queen_node and worker_node can actually USE them. Previously the retrieval
   built a context_injection string and discarded it.
F-27B: pattern keys include swarm_id to avoid cross-session overwrites
F-27C: sona_cycle_count cap is enforced by the field validator (state.py)
"""
from __future__ import annotations

from typing import Any

from ..models.state import SwarmState


def distill_node(state: dict[str, Any]) -> dict[str, Any]:
    """SONA DISTILL + CONSOLIDATE."""
    swarm = SwarmState.model_validate(state)

    if swarm.status not in ("distilling", "completed"):
        swarm.touch()
        return swarm.to_json_dict()

    # ── DISTILL ──────────────────────────────────────────────────────────
    if swarm.config.sona_enabled:
        removed = swarm.memory.distill()
        if removed:
            swarm.append_history("sona_distill", {
                "step": "distill",
                "removed_count": len(removed),
            })

    # ── CONSOLIDATE ──────────────────────────────────────────────────────
    if swarm.config.sona_enabled and swarm.final_output:
        # F-27B: include swarm_id in the key (avoid cross-session overwrites)
        pattern_key = f"pattern:{swarm.swarm_id}:{swarm.objective_hash}:{swarm.iteration}"
        agreement = (
            swarm.consensus_result.agreement_fraction
            if swarm.consensus_result
            else swarm.config.sona_min_confidence
        )
        swarm.memory.store(
            key=pattern_key,
            value=swarm.final_output,
            namespace=swarm.config.memory_namespace,
            score=min(1.0, agreement),
            tags=["sona", "successful_run"],
            source_agent_id="distill_node",
        )
        swarm.append_history("memory_store", {
            "step": "consolidate",
            "key": pattern_key,
            "namespace": swarm.config.memory_namespace,
        })

    swarm.increment_sona()
    swarm.status = "completed"
    swarm.touch()
    return swarm.to_json_dict()


def memory_retrieve_node(state: dict[str, Any]) -> dict[str, Any]:
    """SONA RETRIEVE: write retrieved patterns into state for downstream nodes (F-27A)."""
    swarm = SwarmState.model_validate(state)

    if not swarm.config.sona_enabled:
        return swarm.to_json_dict()

    relevant = swarm.memory.search(
        swarm.objective,
        namespace=swarm.config.memory_namespace,
        top_k=3,
        min_score=swarm.config.sona_min_confidence,
    )

    if relevant:
        # F-27A CRITICAL: write retrieved patterns to state (was discarded before)
        swarm.retrieved_context = [
            {
                "key": e.key,
                "value": e.value[:1024],
                "score": e.score,
                "tags": list(e.tags),
            }
            for e in relevant
        ]
        swarm.append_history("memory_retrieve", {
            "retrieved_count": len(relevant),
            "top_score": relevant[0].score,
        })
        # EWC++-analog: promote scores of accessed entries
        for e in relevant:
            swarm.memory.promote_score(e.key, e.namespace)
    else:
        swarm.retrieved_context = []

    swarm.touch()
    return swarm.to_json_dict()


__all__ = ["distill_node", "memory_retrieve_node"]
