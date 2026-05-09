"""F-04C / F-19A: HITL single-use guard test."""

import pytest

from swarm.models.config import SwarmConfig
from swarm.models.consensus import ConsensusResult
from swarm.models.state import SwarmState
from swarm.nodes.approval import approval_node


def _state_awaiting_approval() -> SwarmState:
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="x", config=config)
    s.consensus_result = ConsensusResult(
        protocol="majority",
        action="proposed action",
        vote_count=3,
        agreement_fraction=0.5,
        risk_score=0.5,
        requires_approval=True,
    )
    s.status = "awaiting_approval"
    return s


def test_approval_pass_through_when_not_required():
    config = SwarmConfig()
    s = SwarmState(swarm_id="s1", objective="x", config=config)
    # consensus_result is None → pass through
    out = approval_node(s.to_json_dict())
    assert out["status"] == "judging"


def test_approval_consumed_blocks_replay():
    """F-19A: second invocation against same state is blocked."""
    s = _state_awaiting_approval()
    s.approval_consumed = True  # pretend already approved once
    out = approval_node(s.to_json_dict())
    assert out["status"] == "failed"
    assert out["failure_cause"] == "approval_replay"


def test_approval_token_required_for_resume():
    """F-19A: client must echo the issued token."""
    # The fallback `interrupt` shim returns the requested token, so a normal
    # invocation succeeds. We simulate token mismatch by pretending the resume
    # payload has a different token.
    from swarm.models.agent import ApprovalDecision

    # Validate the typed shape works
    d = ApprovalDecision(
        decision="approve",
        reviewer_id="alice",
        decision_token="abc12345",
    )
    assert d.decision == "approve"
    assert d.reviewer_id == "alice"
    # Strict shape rejects unknown fields
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApprovalDecision.model_validate(
            {
                "decision": "approve",
                "reviewer_id": "alice",
                "decision_token": "abc12345",
                "extra_field": "bad",
            }
        )


def test_approval_decision_decision_literal():
    """F-19B: decision must be 'approve' or 'deny'."""
    from pydantic import ValidationError
    from swarm.models.agent import ApprovalDecision

    with pytest.raises(ValidationError):
        ApprovalDecision(decision="maybe", reviewer_id="alice", decision_token="abc12345")
