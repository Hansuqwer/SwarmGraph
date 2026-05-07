"""
AGENT 11 — Result Model Specialist
AGENT 17 — Consensus Node Specialist

ConsensusResult model + all 4 consensus implementations (raft, bft, gossip, majority).
Agents 21-24 output merged here by Hive Leader.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from pydantic import Field, model_validator

from .agent import AgentVote
from .base import FrozenModel
from .types import AgentRole, ConsensusProtocol


# ---------------------------------------------------------------------------
# ConsensusResult — output of any consensus round
# ---------------------------------------------------------------------------

class ConsensusResult(FrozenModel):
    """
    The immutable output of a consensus node execution.
    Always produced — even when consensus fails (failed=True).
    """
    protocol: ConsensusProtocol
    action: str | None = None        # Winning action, or None if failed
    action_hash: str = ""
    vote_count: int = Field(..., ge=0)
    agreement_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    authoritative: bool = False      # True = leader-decided (Raft)
    failed: bool = False             # True = quorum not reached
    failure_reason: str = ""
    requires_approval: bool = False  # True = risk above threshold
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistency(self) -> "ConsensusResult":
        if self.failed and self.action is not None:
            raise ValueError("A failed ConsensusResult must not have an action")
        if not self.failed and self.action is None:
            raise ValueError("A successful ConsensusResult must have an action")
        return self


# ---------------------------------------------------------------------------
# AGENT 21 — Raft Consensus (Leader-based, Hierarchical default)
# ---------------------------------------------------------------------------

def raft_consensus(
    votes: list[AgentVote],
    *,
    queen_authoritative: bool = True,
) -> ConsensusResult:
    """
    Raft: queen vote wins unconditionally (authoritative leader).
    If no queen is present, falls back to weighted majority.
    Ruflo: 'use raft consensus for hive-mind (leader maintains authoritative state)'
    """
    if not votes:
        return ConsensusResult(
            protocol="raft",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
        )

    if queen_authoritative:
        queen_votes = [v for v in votes if v.agent_role == "queen"]
        if queen_votes:
            winner = max(queen_votes, key=lambda v: v.confidence)
            return ConsensusResult(
                protocol="raft",
                action=winner.proposed_action,
                vote_count=len(votes),
                agreement_fraction=1.0,
                authoritative=True,
            )

    # Fallback: weighted majority
    return majority_consensus(votes)


# ---------------------------------------------------------------------------
# AGENT 22 — BFT Consensus (Byzantine Fault Tolerant, Star/high-stakes)
# ---------------------------------------------------------------------------

def bft_consensus(
    votes: list[AgentVote],
    *,
    quorum_fraction: float = 0.67,
) -> ConsensusResult:
    """
    BFT: requires >=quorum_fraction supermajority.
    Tolerates up to (1 - quorum_fraction) faulty agents.
    Ruflo: 'Byzantine coordinator — 2/3 majority for BFT'
    """
    if not votes:
        return ConsensusResult(
            protocol="bft",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
        )

    threshold = math.ceil(len(votes) * quorum_fraction)
    counter: Counter[str] = Counter(v.proposed_action for v in votes)

    for action, count in counter.most_common():
        if count >= threshold:
            return ConsensusResult(
                protocol="bft",
                action=action,
                vote_count=len(votes),
                agreement_fraction=count / len(votes),
                authoritative=True,
            )

    # Quorum not reached — fail gracefully (no exception)
    best_action, best_count = counter.most_common(1)[0]
    return ConsensusResult(
        protocol="bft",
        action=None,
        vote_count=len(votes),
        agreement_fraction=best_count / len(votes),
        authoritative=False,
        failed=True,
        failure_reason=(
            f"BFT quorum not reached: best action got {best_count}/{len(votes)} votes "
            f"(need {threshold})"
        ),
    )


# ---------------------------------------------------------------------------
# AGENT 23 — Gossip Consensus (weighted confidence, Mesh topology)
# ---------------------------------------------------------------------------

def gossip_consensus(votes: list[AgentVote]) -> ConsensusResult:
    """
    Gossip: weights each vote by agent confidence. No hard quorum.
    Eventual consistency — best weighted action wins.
    Ruflo: 'Gossip decentralised P2P'
    """
    if not votes:
        return ConsensusResult(
            protocol="gossip",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
        )

    weighted: dict[str, float] = defaultdict(float)
    for v in votes:
        weighted[v.proposed_action] += v.confidence

    total_weight = sum(weighted.values())
    if total_weight == 0.0:
        # All agents had zero confidence — pick by count
        counter: Counter[str] = Counter(v.proposed_action for v in votes)
        best_action = counter.most_common(1)[0][0]
        return ConsensusResult(
            protocol="gossip",
            action=best_action,
            vote_count=len(votes),
            agreement_fraction=0.0,
            authoritative=False,
        )

    best_action = max(weighted, key=lambda a: weighted[a])
    return ConsensusResult(
        protocol="gossip",
        action=best_action,
        vote_count=len(votes),
        agreement_fraction=weighted[best_action] / total_weight,
        authoritative=False,
    )


# ---------------------------------------------------------------------------
# AGENT 24 — Majority Consensus (simple >50%, fallback)
# ---------------------------------------------------------------------------

def majority_consensus(votes: list[AgentVote]) -> ConsensusResult:
    """
    Simple majority: action with most votes wins.
    Tie: pick deterministically by alphabetical order of action string.
    Single voter: always succeeds.
    """
    if not votes:
        return ConsensusResult(
            protocol="majority",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
        )

    counter: Counter[str] = Counter(v.proposed_action for v in votes)
    # Sort by (-count, action) for deterministic tie-breaking
    ranked = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    best_action, best_count = ranked[0]

    return ConsensusResult(
        protocol="majority",
        action=best_action,
        vote_count=len(votes),
        agreement_fraction=best_count / len(votes),
        authoritative=False,
    )


# ---------------------------------------------------------------------------
# Dispatch function (used by consensus_node)
# ---------------------------------------------------------------------------

def run_consensus(
    votes: list[AgentVote],
    protocol: ConsensusProtocol,
    *,
    bft_quorum: float = 0.67,
    queen_authoritative: bool = True,
    risk_threshold: float = 0.8,
) -> ConsensusResult:
    """
    Route to the correct consensus implementation based on protocol.
    Adds risk_score and requires_approval flag to the result.
    """
    if protocol == "raft":
        result = raft_consensus(votes, queen_authoritative=queen_authoritative)
    elif protocol == "bft":
        result = bft_consensus(votes, quorum_fraction=bft_quorum)
    elif protocol == "gossip":
        result = gossip_consensus(votes)
    else:  # majority
        result = majority_consensus(votes)

    # Compute risk score: inverse of agreement fraction
    risk = 1.0 - result.agreement_fraction if not result.failed else 1.0
    requires_approval = risk >= risk_threshold

    # Return a new ConsensusResult with risk metadata
    return ConsensusResult(
        **{
            **result.model_dump(),
            "risk_score": risk,
            "requires_approval": requires_approval,
        }
    )
