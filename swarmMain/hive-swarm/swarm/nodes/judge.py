"""
AGENT 18 — Judge Node Specialist
AGENT 05 — Risk & Drift Control

Anti-drift validation, quality judgment, retry routing, SONA distill trigger.
"""
from __future__ import annotations

from typing import Any

from ..models.state import SwarmState


def judge_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node.
    Validates consensus output against the original objective (anti-drift).
    Triggers SONA distillation. Routes to completed or retry.

    Ruflo: 'hierarchical coordinators validate outputs against original goals'
    """
    swarm = SwarmState.model_validate(state)
    swarm.status = "judging"

    candidate = swarm.latest_output or (
        swarm.consensus_result.action if swarm.consensus_result else ""
    )

    if not candidate.strip():
        swarm.fail("all_workers_failed", "Judge received empty output from consensus")
        swarm.append_history("judge", {"outcome": "empty_output"})
        swarm.touch()
        return swarm.to_json_dict()

    # Anti-drift check (Agent 05)
    drift_ok = swarm.check_drift(candidate)
    if not drift_ok and swarm.config.anti_drift_enabled:
        swarm.fail(
            "objective_drift",
            f"Output does not satisfy objective (hash={swarm.objective_hash})",
        )
        swarm.append_history("drift_detected", {
            "objective_hash": swarm.objective_hash,
            "candidate_preview": candidate[:100],
        })
        swarm.touch()
        return swarm.to_json_dict()

    # Accepted — set final output
    swarm.final_output = candidate
    swarm.status = "distilling"   # trigger SONA distill next

    swarm.append_history("judge", {
        "outcome": "accepted",
        "drift_check": "passed",
        "output_hash": swarm.latest_output_hash,
    })
    swarm.touch()
    return swarm.to_json_dict()


def route_after_judge(state: dict[str, Any]) -> str:
    """
    Conditional edge: completed → distill_node (then END),
                      failed   → end (or retry if under max_iterations).
    """
    swarm = SwarmState.model_validate(state)
    if swarm.status == "failed":
        if swarm.iteration < swarm.config.max_iterations:
            return "route_task"  # retry loop
        return "end"
    return "distill_node"
