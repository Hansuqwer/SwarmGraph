"""
AGENT 19 — Approval Node Specialist
Human-in-the-loop interrupt() gate for high-risk consensus decisions.
Ruflo: Claims-based human-agent coordination.
"""
from __future__ import annotations

from typing import Any

from ..models.state import SwarmState

try:
    from langgraph.types import interrupt
    _HAS_INTERRUPT = True
except ImportError:  # pragma: no cover
    _HAS_INTERRUPT = False
    def interrupt(payload: dict) -> dict:  # type: ignore[misc]
        return {"decision": "approve"}  # fallback for tests


def approval_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node.
    Pauses execution for human review when consensus risk > threshold.

    Interrupt payload contains everything the human needs to decide:
      - swarm_id, objective, proposed action, vote breakdown, risk score.

    On resume: Command(resume={"decision": "approve" | "deny"})

    Ruflo: 'Claims — Human-Agent Coord'
    """
    swarm = SwarmState.model_validate(state)

    if swarm.consensus_result is None or not swarm.consensus_result.requires_approval:
        # No approval needed — pass through
        swarm.status = "judging"
        swarm.touch()
        return swarm.to_json_dict()

    # Build interrupt payload (minimal — no secrets)
    payload = interrupt({
        "swarm_id": swarm.swarm_id,
        "objective": swarm.objective,
        "proposed_action": swarm.consensus_result.action,
        "risk_score": swarm.consensus_result.risk_score,
        "agreement_fraction": swarm.consensus_result.agreement_fraction,
        "vote_count": swarm.consensus_result.vote_count,
        "protocol": swarm.consensus_result.protocol,
    })

    # Execution resumes here after Command(resume={...}) is issued
    decision = str(payload.get("decision", "deny")).lower().strip()

    swarm.append_history("approval_decision", {
        "decision": decision,
        "risk_score": swarm.consensus_result.risk_score,
        "proposed_action_preview": (swarm.consensus_result.action or "")[:100],
    })

    if decision == "approve":
        swarm.status = "judging"
    else:
        swarm.status = "denied"
        swarm.failure_cause = "approval_denied"
        swarm.add_error(f"Approval denied by human reviewer (risk={swarm.consensus_result.risk_score:.2f})")

    swarm.touch()
    return swarm.to_json_dict()


def route_after_approval(state: dict[str, Any]) -> str:
    """Conditional edge after approval_node."""
    swarm = SwarmState.model_validate(state)
    if swarm.status == "denied":
        return "end"
    return "judge_node"
