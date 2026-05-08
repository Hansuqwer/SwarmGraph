"""Consensus node — patched (v8: signs the consensus_result event).

History (v4–v7.1) preserved; v8 adds the sign_and_record() call.
"""
from __future__ import annotations

import secrets
from typing import Any

from .._audit_helper import sign_and_record
from ..models.consensus import run_consensus
from ..models.state import SwarmState


def consensus_node(state: dict[str, Any]) -> dict[str, Any]:
    swarm = SwarmState.model_validate(state)

    if not swarm.consensus_round_id:
        swarm.consensus_round_id = secrets.token_hex(8)

    if not swarm.pending_votes:
        swarm.fail(
            "consensus_failed",
            "Consensus node received zero votes — all workers may have failed",
        )
        swarm.append_history("consensus_failed", {
            "outcome": "no_votes",
            "round_id": swarm.consensus_round_id,
        })
        # v8: sign the failure too
        sign_and_record(swarm, "consensus_result", {
            "round_id": swarm.consensus_round_id,
            "failed": True,
            "reason": "no_votes",
            "vote_count": 0,
        })
        swarm.touch()
        return swarm.to_json_dict()

    result = run_consensus(
        votes=swarm.pending_votes,
        protocol=swarm.config.consensus_protocol,
        bft_quorum=swarm.config.bft_quorum_fraction,
        queen_authoritative=swarm.config.raft_queen_authoritative,
        risk_threshold=swarm.config.require_approval_above_risk,
        min_voters=swarm.config.require_min_voters,
    )

    swarm.consensus_result = result
    swarm.pending_votes = []

    if result.failed:
        if "Split-brain" in result.failure_reason:
            swarm.append_history("split_brain_detected", {
                "round_id": swarm.consensus_round_id,
                "reason": result.failure_reason,
            })
            swarm.failure_cause = "split_brain"
        else:
            swarm.append_history("consensus_failed", {
                "round_id": swarm.consensus_round_id,
                "protocol": result.protocol,
                "vote_count": result.vote_count,
                "agreement": result.agreement_fraction,
                "reason": result.failure_reason,
            })
        swarm.fail(
            swarm.failure_cause or "consensus_failed",
            result.failure_reason or "Consensus failed",
        )
    else:
        swarm.latest_output = result.action or ""
        swarm.status = "judging" if not result.requires_approval else "awaiting_approval"

    swarm.append_history("consensus", {
        "round_id": swarm.consensus_round_id,
        "protocol": result.protocol,
        "vote_count": result.vote_count,
        "agreement": result.agreement_fraction,
        "failed": result.failed,
        "requires_approval": result.requires_approval,
        "risk_score": result.risk_score,
        "dissenter_count": len(result.dissenter_ids),
    })

    # v8: sign the consensus result. Truncate action preview so audit lines
    # stay under the 4KB JSONL append safety limit.
    sign_and_record(swarm, "consensus_result", {
        "round_id": swarm.consensus_round_id,
        "protocol": result.protocol,
        "vote_count": result.vote_count,
        "agreement_fraction": result.agreement_fraction,
        "risk_score": result.risk_score,
        "requires_approval": result.requires_approval,
        "failed": result.failed,
        "failure_reason": result.failure_reason[:200] if result.failure_reason else "",
        "action_preview": (result.action or "")[:500],
        "dissenter_count": len(result.dissenter_ids),
    })

    swarm.touch()
    return swarm.to_json_dict()


def route_after_consensus(state: dict[str, Any]) -> str:
    swarm = SwarmState.model_validate(state)
    if swarm.status == "failed":
        return "end"
    if swarm.status == "awaiting_approval":
        return "approval_node"
    return "judge_node"


__all__ = ["consensus_node", "route_after_consensus"]
