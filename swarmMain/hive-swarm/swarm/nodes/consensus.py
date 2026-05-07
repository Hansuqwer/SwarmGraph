"""
AGENT 17 — Consensus Node Specialist
Runs the configured consensus protocol over pending_votes.
Handles empty/tied votes. Sets consensus_result in SwarmState.
"""
from __future__ import annotations

from typing import Any

from ..models.consensus import run_consensus
from ..models.state import SwarmState


def consensus_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node.
    Applies the configured consensus protocol to swarm.pending_votes.
    Writes ConsensusResult back into state.

    Safeguards:
      - Zero votes → failed ConsensusResult (no exception)
      - Tied votes → deterministic tie-break (alphabetical)
      - BFT quorum miss → failed=True, failure_reason set
    """
    swarm = SwarmState.model_validate(state)

    if not swarm.pending_votes:
        swarm.fail(
            "consensus_failed",
            "Consensus node received zero votes — all workers may have failed",
        )
        swarm.append_history("consensus", {"node": "consensus", "outcome": "no_votes"})
        swarm.touch()
        return swarm.to_json_dict()

    result = run_consensus(
        votes=swarm.pending_votes,
        protocol=swarm.config.consensus_protocol,
        bft_quorum=swarm.config.bft_quorum_fraction,
        queen_authoritative=swarm.config.raft_queen_authoritative,
        risk_threshold=swarm.config.require_approval_above_risk,
    )

    swarm.consensus_result = result
    swarm.pending_votes = []  # Clear votes after consensus

    if result.failed:
        swarm.fail(
            "consensus_failed",
            result.failure_reason or "Consensus failed (quorum not reached)",
        )
    else:
        swarm.latest_output = result.action or ""
        swarm.status = "judging" if not result.requires_approval else "awaiting_approval"

    swarm.append_history("consensus", {
        "node": "consensus",
        "protocol": result.protocol,
        "vote_count": result.vote_count,
        "agreement": result.agreement_fraction,
        "failed": result.failed,
        "requires_approval": result.requires_approval,
        "risk_score": result.risk_score,
    })
    swarm.touch()
    return swarm.to_json_dict()


def route_after_consensus(state: dict[str, Any]) -> str:
    """
    Conditional edge after consensus_node.
    Routes to approval_node if high-risk, judge_node otherwise, or END if failed.
    """
    swarm = SwarmState.model_validate(state)
    if swarm.status == "failed":
        return "end"
    if swarm.status == "awaiting_approval":
        return "approval_node"
    return "judge_node"
