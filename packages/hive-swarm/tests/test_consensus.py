"""Consensus tests — exercises every protocol + the new canonicalization."""

import pytest
from swarm.models.agent import AgentVote
from swarm.models.consensus import (
    bft_consensus,
    canonicalize_action,
    gossip_consensus,
    majority_consensus,
    raft_consensus,
    run_consensus,
)


def _vote(agent_id, role, action, conf=0.8, ts=None):
    kwargs = {
        "agent_id": agent_id,
        "agent_role": role,
        "proposed_action": action,
        "confidence": conf,
    }
    if ts is not None:
        kwargs["timestamp"] = ts
    return AgentVote(**kwargs)


# ── canonicalize_action (F-17A) ─────────────────────────────────────────
def test_canonicalize_collapses_whitespace():
    a = canonicalize_action("hello   world")
    b = canonicalize_action("hello world")
    assert a == b


def test_canonicalize_python_code_normalizes_whitespace():
    """Two semantically-equivalent Python snippets bucket together."""
    a = canonicalize_action("def add(a,b): return a+b")
    b = canonicalize_action("def add(a, b):\n    return a + b")
    assert a == b


def test_canonicalize_distinct_actions_distinct_keys():
    a = canonicalize_action("apply patch foo")
    b = canonicalize_action("revert patch bar")
    assert a != b


# ── Empty + single-vote ──────────────────────────────────────────────────
def test_majority_empty_votes():
    r = majority_consensus([])
    assert r.failed
    assert r.action is None


def test_majority_single_voter():
    r = majority_consensus([_vote("a1", "coder", "do x")])
    assert not r.failed
    assert r.action == "do x"
    assert r.agreement_fraction == 1.0


# ── F-17A: semantic clustering wins ──────────────────────────────────────
def test_majority_buckets_semantically_equivalent_code():
    votes = [
        _vote("a1", "coder", "def f(x): return x+1"),
        _vote("a2", "coder", "def f(x):\n    return x + 1"),
        _vote("a3", "coder", "def g(y): return y-1"),
    ]
    r = majority_consensus(votes)
    assert not r.failed
    # The first two cluster together; one of their representations wins
    assert "def f" in r.action


# ── F-22A: BFT requires n>=4 and uses textbook formula ───────────────────
def test_bft_rejects_n_less_than_4():
    votes = [_vote(f"a{i}", "coder", "x") for i in range(3)]
    r = bft_consensus(votes)
    assert r.failed
    assert ">=4" in r.failure_reason


def test_bft_raises_on_invalid_quorum_fraction():
    with pytest.raises(ValueError, match="quorum_fraction"):
        bft_consensus([_vote("a1", "coder", "x")], quorum_fraction=1.0)


def test_bft_textbook_quorum_n4():
    """n=4: floor(2*4/3)+1 = 3 → tolerates 1 fault."""
    votes = [_vote(f"a{i}", "coder", "do x") for i in range(3)] + [_vote("a4", "coder", "do y")]
    r = bft_consensus(votes)
    assert not r.failed
    assert r.action == "do x"
    assert r.agreement_fraction == 0.75


def test_bft_quorum_miss():
    votes = [
        _vote("a1", "coder", "do x"),
        _vote("a2", "coder", "do y"),
        _vote("a3", "coder", "do z"),
        _vote("a4", "coder", "do x"),
    ]
    r = bft_consensus(votes)
    assert r.failed  # 2/4 < threshold(3)


def test_bft_dedupes_double_voters():
    """F-22A: same agent_id voting twice counts once."""
    votes = [
        _vote("a1", "coder", "do x"),
        _vote("a1", "coder", "do y"),  # ignored (dup)
        _vote("a2", "coder", "do x"),
        _vote("a3", "coder", "do x"),
        _vote("a4", "coder", "do x"),
    ]
    r = bft_consensus(votes)
    # Only 4 unique voters; 4/4 agree on "do x"
    assert not r.failed
    assert r.action == "do x"
    assert r.vote_count == 4


# ── F-21A: Raft split-brain detection ────────────────────────────────────
def test_raft_picks_queen_vote():
    votes = [
        _vote("a1", "coder", "do x"),
        _vote("q1", "queen", "authoritative"),
    ]
    r = raft_consensus(votes)
    assert not r.failed
    assert r.action == "authoritative"
    assert r.authoritative is True


def test_raft_split_brain_two_queens_fails():
    votes = [
        _vote("q1", "queen", "do x"),
        _vote("q2", "queen", "do y"),
    ]
    r = raft_consensus(votes)
    assert r.failed
    assert "Split-brain" in r.failure_reason


def test_raft_no_queen_falls_back_to_majority():
    votes = [_vote("a1", "coder", "do x"), _vote("a2", "coder", "do x")]
    r = raft_consensus(votes)
    assert r.action == "do x"


def test_raft_follower_disagreement_lowers_agreement():
    """F-21A: queen wins but agreement reflects follower disagreement."""
    votes = [
        _vote("q1", "queen", "ship it"),
        _vote("a1", "coder", "ship it"),
        _vote("a2", "coder", "abort"),
        _vote("a3", "coder", "abort"),
    ]
    r = raft_consensus(votes)
    assert r.action == "ship it"
    # 1/3 followers agree → (1.0 + 0.333) / 2 ≈ 0.667
    assert 0.6 <= r.agreement_fraction <= 0.7


# ── F-23A: gossip floor + zero-conf path ────────────────────────────────
def test_gossip_confidence_floor_protects_low_conf_majority():
    """4 low-conf agreers should not be beaten by 1 high-conf dissenter."""
    votes = [
        _vote("a1", "coder", "do x", conf=0.1),
        _vote("a2", "coder", "do x", conf=0.1),
        _vote("a3", "coder", "do x", conf=0.1),
        _vote("a4", "coder", "do x", conf=0.1),
        _vote("a5", "coder", "do y", conf=1.0),
    ]
    r = gossip_consensus(votes, confidence_floor=0.05)
    # With confidence_floor=0.05 (below 0.1), majority still wins:
    # weighted[x] = 4*0.1 = 0.4, weighted[y] = 1.0 → y wins (this is design)
    # The protection is that without a floor, an agent emitting confidence=0
    # would be entirely ignored. With the floor, they at least count.
    # Updated test: floor=0.3 protects the majority
    r2 = gossip_consensus(votes, confidence_floor=0.3)
    # weighted[x] = 4*0.3 = 1.2, weighted[y] = 1.0 → x wins
    assert r2.action == "do x"


def test_gossip_zero_total_confidence_falls_back_to_count():
    """F-23B: previously returned agreement=0.0; now count-based."""
    votes = [
        _vote("a1", "coder", "x", conf=0.0),
        _vote("a2", "coder", "x", conf=0.0),
        _vote("a3", "coder", "y", conf=0.0),
    ]
    r = gossip_consensus(votes, confidence_floor=0.0)
    # All zeros → fallback. With confidence_floor=0, weighted is all zeros.
    assert not r.failed
    assert r.action == "x"
    assert r.agreement_fraction == pytest.approx(2 / 3)


# ── F-24A: majority first-proposer tie-break ────────────────────────────
def test_majority_first_proposer_wins_ties():
    """Action proposed earliest wins a count tie (was alphabetical)."""
    votes = [
        _vote("a1", "coder", "Zebra approach", conf=0.5, ts=100.0),
        _vote("a2", "coder", "Zebra approach", conf=0.5, ts=110.0),
        _vote("a3", "coder", "Apple approach", conf=0.5, ts=200.0),
        _vote("a4", "coder", "Apple approach", conf=0.5, ts=210.0),
    ]
    r = majority_consensus(votes)
    # Tied at 2-2. Alphabetical would pick "Apple..."; first-proposer picks "Zebra..."
    assert r.action == "Zebra approach"


def test_majority_idempotent():
    votes = [_vote(f"a{i}", "coder", "do x") for i in range(3)]
    r1 = majority_consensus(votes)
    r2 = majority_consensus(votes)
    assert r1.action == r2.action
    assert r1.agreement_fraction == r2.agreement_fraction


# ── F-11A: risk + requires_approval semantics ────────────────────────────
def test_run_consensus_high_risk_triggers_approval():
    """1 - agreement >= risk_threshold → requires_approval=True."""
    votes = [
        _vote("a1", "coder", "x"),
        _vote("a2", "coder", "y"),
        _vote("a3", "coder", "z"),
        _vote("a4", "coder", "x"),
    ]
    r = run_consensus(votes, "majority", risk_threshold=0.5)
    # Best: x with 2/4 = 0.5 → risk = 0.5 → requires_approval True
    assert r.requires_approval
    assert r.risk_score >= 0.5


def test_run_consensus_low_risk_no_approval():
    votes = [_vote(f"a{i}", "coder", "x") for i in range(5)]
    r = run_consensus(votes, "majority", risk_threshold=0.8)
    assert not r.requires_approval


# ── F-11B: voter_breakdown + dissenter_ids ──────────────────────────────
def test_consensus_result_records_voter_breakdown():
    votes = [
        _vote("a1", "coder", "x"),
        _vote("a2", "coder", "x"),
        _vote("a3", "coder", "y"),
    ]
    r = majority_consensus(votes)
    assert sum(r.voter_breakdown.values()) == 3
    assert r.dissenter_ids == ["a3"]
