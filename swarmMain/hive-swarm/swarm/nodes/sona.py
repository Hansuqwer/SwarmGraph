"""
AGENT 27 — SONA Loop Specialist
RETRIEVE → JUDGE → DISTILL → CONSOLIDATE → ROUTE — closed as a LangGraph cycle.
"""
from __future__ import annotations

from typing import Any

from ..models.base import stable_hash, now_ts
from ..models.state import SwarmState


def distill_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    SONA DISTILL + CONSOLIDATE step (LangGraph node).
    Runs after judge_node accepts an output.

    1. DISTILL: prune low-confidence memory entries (SONA min_score filter)
    2. CONSOLIDATE: store successful pattern; promote score of retrieved entries
    3. Increment SONA cycle counter
    4. Transition to completed

    Ruflo: RETRIEVE → JUDGE → DISTILL → CONSOLIDATE → ROUTE (loop)
    """
    swarm = SwarmState.model_validate(state)

    if swarm.status not in ("distilling", "completed"):
        # Guard: only run if judge accepted output
        swarm.touch()
        return swarm.to_json_dict()

    # ── DISTILL ──────────────────────────────────────────────────────────────
    if swarm.config.sona_enabled:
        removed = swarm.memory.distill()
        if removed:
            swarm.append_history("sona_distill", {
                "step": "distill",
                "removed_count": len(removed),
            })

    # ── CONSOLIDATE ───────────────────────────────────────────────────────────
    if swarm.config.sona_enabled and swarm.final_output:
        pattern_key = f"pattern:{swarm.objective_hash}:{swarm.iteration}"
        swarm.memory.store(
            key=pattern_key,
            value=swarm.final_output,
            namespace=swarm.config.memory_namespace,
            score=min(
                1.0,
                (swarm.consensus_result.agreement_fraction if swarm.consensus_result else 0.5),
            ),
            tags=["sona", "successful_run"],
            source_agent_id="distill_node",
        )
        swarm.append_history("memory_store", {
            "step": "consolidate",
            "key": pattern_key,
            "namespace": swarm.config.memory_namespace,
        })

    # ── ROUTE (cycle increment) ───────────────────────────────────────────────
    swarm.increment_sona()
    swarm.status = "completed"
    swarm.touch()
    return swarm.to_json_dict()


def memory_retrieve_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    SONA RETRIEVE step — runs before routing, injects relevant past patterns
    into SwarmState so the queen/workers can leverage memory.
    Ruflo: 'memory search --query "task keywords"'
    """
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
        # Inject retrieved patterns into task context (available to queen + workers)
        context_injection = "\n".join(
            f"[PATTERN score={e.score:.2f}] {e.value}"
            for e in relevant
        )
        swarm.append_history("memory_retrieve", {
            "retrieved_count": len(relevant),
            "top_score": relevant[0].score if relevant else 0.0,
        })

        # Promote accessed entries (EWC++ analog)
        for e in relevant:
            swarm.memory.promote_score(e.key, e.namespace)

    return swarm.to_json_dict()
