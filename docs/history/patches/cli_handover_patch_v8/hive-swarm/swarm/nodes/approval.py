"""Approval / HITL node — patched (v8: signs every approval_decision).

History (v4–v7.1) preserved; v8 adds sign_and_record() for both
issued tokens and operator decisions.
"""
from __future__ import annotations

import secrets
from typing import Any

from pydantic import ValidationError

from .._audit_helper import sign_and_record
from ..models.agent import ApprovalDecision
from ..models.state import SwarmState

try:
    from langgraph.types import interrupt
    _HAS_INTERRUPT = True
except ImportError:  # pragma: no cover
    _HAS_INTERRUPT = False
    def interrupt(payload: dict) -> dict:  # type: ignore[misc]
        return {
            "decision": "approve",
            "reviewer_id": "test-fallback",
            "decision_token": payload.get("decision_token_required", "test-token"),
        }


_PREVIEW_MAX = 2048


def approval_node(state: dict[str, Any]) -> dict[str, Any]:
    swarm = SwarmState.model_validate(state)

    if swarm.consensus_result is None or not swarm.consensus_result.requires_approval:
        swarm.status = "judging"
        swarm.touch()
        return swarm.to_json_dict()

    # F-19A single-use guard
    if swarm.approval_consumed:
        swarm.append_history("approval_replay_blocked", {
            "swarm_id": swarm.swarm_id,
            "reason": "approval already consumed for this swarm; refusing replay",
        })
        # v8: sign the replay-block too
        sign_and_record(swarm, "approval_decision", {
            "decision": "replay_blocked",
            "reviewer_id": "<framework>",
            "reason": "approval_consumed=True",
        })
        swarm.fail(
            "approval_replay",
            "Approval already consumed for this swarm; refusing replay",
        )
        swarm.touch()
        return swarm.to_json_dict()

    expected_token = secrets.token_hex(16)
    swarm.approval_decision_token = expected_token

    action = swarm.consensus_result.action or ""
    truncated = len(action) > _PREVIEW_MAX

    raw = interrupt({
        "swarm_id": swarm.swarm_id,
        "objective_preview": swarm.objective[:1024],
        "proposed_action_preview": action[:_PREVIEW_MAX],
        "action_truncated": truncated,
        "risk_score": swarm.consensus_result.risk_score,
        "agreement_fraction": swarm.consensus_result.agreement_fraction,
        "vote_count": swarm.consensus_result.vote_count,
        "dissenter_count": len(swarm.consensus_result.dissenter_ids),
        "protocol": swarm.consensus_result.protocol,
        "decision_token_required": expected_token,
    })

    try:
        decision = ApprovalDecision.model_validate(raw)
    except ValidationError as e:
        swarm.add_error(f"approval_node: invalid resume payload: {e}")
        swarm.status = "denied"
        swarm.failure_cause = "approval_denied"
        swarm.append_history("approval_decision", {
            "decision": "deny_invalid_payload",
            "reason": str(e),
        })
        # v8
        sign_and_record(swarm, "approval_decision", {
            "decision": "deny_invalid_payload",
            "reviewer_id": "<framework>",
            "error": str(e)[:500],
        })
        swarm.touch()
        return swarm.to_json_dict()

    if decision.decision_token != expected_token:
        swarm.add_error(
            f"approval_node: decision_token mismatch (expected {expected_token[:8]}…)"
        )
        swarm.status = "denied"
        swarm.failure_cause = "approval_denied"
        swarm.append_history("approval_decision", {
            "decision": "deny_token_mismatch",
            "reviewer_id": decision.reviewer_id,
        })
        # v8
        sign_and_record(swarm, "approval_decision", {
            "decision": "deny_token_mismatch",
            "reviewer_id": decision.reviewer_id,
        })
        swarm.touch()
        return swarm.to_json_dict()

    swarm.approval_consumed = True

    swarm.append_history("approval_decision", {
        "decision": decision.decision,
        "reviewer_id": decision.reviewer_id,
        "risk_score": swarm.consensus_result.risk_score,
        "proposed_action_preview": action[:200],
    })

    # v8: sign the decision (with reviewer_id captured)
    sign_and_record(swarm, "approval_decision", {
        "decision": decision.decision,
        "reviewer_id": decision.reviewer_id,
        "risk_score": swarm.consensus_result.risk_score,
        "agreement_fraction": swarm.consensus_result.agreement_fraction,
        "action_preview": action[:500],
        "reason": decision.reason[:500],
    })

    if decision.decision == "approve":
        swarm.status = "judging"
    else:
        swarm.status = "denied"
        swarm.failure_cause = "approval_denied"
        swarm.add_error(
            f"Approval denied by {decision.reviewer_id} "
            f"(risk={swarm.consensus_result.risk_score:.2f}): {decision.reason}"
        )

    swarm.touch()
    return swarm.to_json_dict()


def route_after_approval(state: dict[str, Any]) -> str:
    swarm = SwarmState.model_validate(state)
    if swarm.status in ("denied", "failed"):
        return "end"
    return "judge_node"


__all__ = ["approval_node", "route_after_approval"]
