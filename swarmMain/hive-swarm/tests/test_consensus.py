"""
AGENT 29 — Test Engineer
Test suite 2/5: Consensus correctness (all 4 protocols + edge cases).
"""
from __future__ import annotations

import pytest

from swarm.models.agent import AgentVote
from swarm.models.consensus import (
    bft_consensus,
    gossip_consensus,
    majority_consensus,
    raft_consensus,
    run_consensus,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _vote(action: str, role="coder", confidence: float = 0.8, agent_id: str = "a") -> AgentVote:
    return AgentVote(
        agent_id=agent_id,
        agent_role=role,
        proposed_action=action,
        confidence=confidence,
    )


# ── Raft (Agent 21) ──────────────────────────────────────────────────────────

class TestRaftConsensus:
    def test_queen_vote_wins(self):
        votes = [
            _vote("action-A", role="coder", agent_id="c1"),
            _vote("action-A", role="coder", agent_id="c2"),
            _vote("action-B", role="queen", agent_id="queen-1"),   # queen vote
        ]
        result = raft_consensus(votes, queen_authoritative=True)
        assert result.action == "action-B"
        assert result.authoritative is True
        assert result.protocol == "raft"

    def test_no_queen_falls_back_to_majority(self):
        votes = [
            _vote("action-A", role="coder", agent_id="c1"),
            _vote("action-A", role="tester", agent_id="t1"),
            _vote("action-B", role="reviewer", agent_id="r1"),
        ]
        result = raft_consensus(votes, queen_authoritative=True)
        assert result.action == "action-A"

    def test_empty_votes_fail_gracefully(self):
        result = raft_consensus([])
        assert result.failed is True
        assert result.action is None
        assert "No votes" in result.failure_reason

    def test_single_queen_vote_wins(self):
        votes = [_vote("solo-action", role="queen", agent_id="q1")]
        result = raft_consensus(votes)
        assert result.action == "solo-action"
        assert result.authoritative is True

    def test_raft_disabled_uses_majority(self):
        votes = [
            _vote("action-X", role="coder", agent_id="c1"),
            _vote("action-X", role="tester", agent_id="t1"),
            _vote("action-Y", role="queen", agent_id="q1"),   # queen present
        ]
        result = raft_consensus(votes, queen_authoritative=False)
        # Queen is not authoritative — majority wins
        assert result.action == "action-X"


# ── BFT (Agent 22) ───────────────────────────────────────────────────────────

class TestBFTConsensus:
    def test_supermajority_succeeds(self):
        votes = [_vote("safe-action", agent_id=f"a{i}") for i in range(5)]
        votes.append(_vote("other-action", agent_id="bad"))
        result = bft_consensus(votes, quorum_fraction=0.67)
        assert result.action == "safe-action"
        assert result.failed is False

    def test_quorum_not_reached_fails_gracefully(self):
        votes = [
            _vote("action-A", agent_id="a1"),
            _vote("action-B", agent_id="a2"),
            _vote("action-C", agent_id="a3"),
        ]
        result = bft_consensus(votes, quorum_fraction=0.67)
        assert result.failed is True
        assert result.action is None
        assert result.failure_reason != ""

    def test_empty_votes_fail_gracefully(self):
        result = bft_consensus([])
        assert result.failed is True

    def test_single_voter_succeeds(self):
        votes = [_vote("only-action", agent_id="solo")]
        result = bft_consensus(votes, quorum_fraction=0.67)
        assert result.action == "only-action"
        assert result.failed is False

    def test_all_tied_fails(self):
        votes = [
            _vote("A", agent_id="a1"),
            _vote("B", agent_id="a2"),
            _vote("C", agent_id="a3"),
            _vote("D", agent_id="a4"),
        ]
        result = bft_consensus(votes, quorum_fraction=0.67)
        assert result.failed is True


# ── Gossip (Agent 23) ────────────────────────────────────────────────────────

class TestGossipConsensus:
    def test_highest_weighted_wins(self):
        votes = [
            _vote("action-A", confidence=0.9, agent_id="a1"),
            _vote("action-A", confidence=0.8, agent_id="a2"),
            _vote("action-B", confidence=0.3, agent_id="a3"),
        ]
        result = gossip_consensus(votes)
        assert result.action == "action-A"
        assert result.protocol == "gossip"

    def test_zero_confidence_votes_use_count(self):
        votes = [
            _vote("action-X", confidence=0.0, agent_id="x1"),
            _vote("action-X", confidence=0.0, agent_id="x2"),
            _vote("action-Y", confidence=0.0, agent_id="y1"),
        ]
        result = gossip_consensus(votes)
        # Falls back to count-based — action-X wins
        assert result.action == "action-X"

    def test_empty_votes_fail_gracefully(self):
        result = gossip_consensus([])
        assert result.failed is True


# ── Majority (Agent 24) ──────────────────────────────────────────────────────

class TestMajorityConsensus:
    def test_simple_majority_wins(self):
        votes = [
            _vote("A", agent_id="a1"),
            _vote("A", agent_id="a2"),
            _vote("B", agent_id="a3"),
        ]
        result = majority_consensus(votes)
        assert result.action == "A"

    def test_tie_resolved_deterministically(self):
        votes = [
            _vote("beta", agent_id="a1"),
            _vote("alpha", agent_id="a2"),
        ]
        r1 = majority_consensus(votes)
        r2 = majority_consensus(votes)
        assert r1.action == r2.action   # must be deterministic

    def test_single_voter_succeeds(self):
        votes = [_vote("solo-action", agent_id="solo")]
        result = majority_consensus(votes)
        assert result.action == "solo-action"
        assert result.failed is False

    def test_empty_votes_fail_gracefully(self):
        result = majority_consensus([])
        assert result.failed is True


# ── run_consensus dispatcher ─────────────────────────────────────────────────

class TestRunConsensus:
    def test_all_protocols_dispatch_correctly(self):
        votes = [_vote("the-action", agent_id=f"a{i}") for i in range(3)]
        for protocol in ("raft", "bft", "gossip", "majority"):
            result = run_consensus(votes, protocol)  # type: ignore[arg-type]
            assert result.protocol == protocol
            assert not result.failed

    def test_risk_score_set(self):
        votes = [_vote("action", agent_id="a1")]
        result = run_consensus(votes, "majority")
        assert 0.0 <= result.risk_score <= 1.0

    def test_requires_approval_above_threshold(self):
        # Force a single vote — agreement = 1.0 → risk = 0.0 → no approval needed
        votes = [_vote("action", agent_id="a1")]
        result = run_consensus(votes, "majority", risk_threshold=0.5)
        assert result.requires_approval is False

    def test_requires_approval_when_risk_high(self):
        # 3 agents, 3 different actions → agreement very low → high risk
        votes = [
            _vote("A", agent_id="a1"),
            _vote("B", agent_id="a2"),
            _vote("C", agent_id="a3"),
        ]
        result = run_consensus(votes, "majority", risk_threshold=0.1)
        assert result.requires_approval is True
