"""ConsensusResult + 4 consensus protocols — patched.

F-17A: canonicalize_action() normalises whitespace + Python-AST hash for code-like
       outputs; vote bucketing uses the canonical form so semantically-equivalent
       paraphrases bucket together. (Embedding-based clustering is the next step;
       requires a real vector adapter — tracked as F-17A-followup.)
F-21A: Raft split-brain detection (multiple queens) + follower-aware agreement
F-22A: textbook PBFT formula (floor(2n/3)+1) + n>=4 minimum + agent de-dupe
F-22C: defensive quorum_fraction<1.0 assertion inside bft_consensus
F-23A: gossip confidence_floor + min_voters
F-23B: zero-confidence success uses count-based agreement (not 0.0)
F-24A: majority first-proposer tie-break (replaces alphabetical bias)
F-11A: risk_score docstring clarifies it is "disagreement"
F-11B: ConsensusResult gains voter_breakdown and dissenter_ids
F-17C: every consensus failure path logs a history entry (handled in nodes/consensus.py)
"""

from __future__ import annotations

import ast
import math
import re
from collections import Counter, defaultdict
from typing import Any

from pydantic import Field, model_validator

from .agent import AgentVote
from .base import FrozenModel
from .types import ConsensusProtocol

# ── Canonicalisation (F-17A) ───────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")


def canonicalize_action(action: str) -> str:
    """Map an action string to a canonical bucketing key.

    Strategy:
      1. Try Python AST hash: parse as code, dump the AST → semantically-equivalent
         code (different whitespace/comments) hashes identically.
      2. Fall back to whitespace-collapsed lowercased text.

    Returns a stable string suitable as a dict key.
    """
    if not action or not isinstance(action, str):
        return action
    stripped = action.strip()

    # Try AST hash for code-like content
    if any(kw in stripped for kw in ("def ", "class ", "import ", "return ", "lambda ")):
        try:
            tree = ast.parse(stripped)
            return f"ast::{ast.dump(tree, annotate_fields=False)}"
        except (SyntaxError, ValueError):
            pass

    # Whitespace-canonical text fallback
    return f"text::{_WHITESPACE_RE.sub(' ', stripped.lower())}"


def _bucket_votes(votes: list[AgentVote]) -> dict[str, list[AgentVote]]:
    """Bucket votes by canonical action key. F-17A."""
    buckets: dict[str, list[AgentVote]] = defaultdict(list)
    for v in votes:
        buckets[canonicalize_action(v.proposed_action)].append(v)
    return buckets


def _representative_action(bucket: list[AgentVote]) -> str:
    """Pick the highest-confidence action string as the bucket representative."""
    return max(bucket, key=lambda v: v.confidence).proposed_action


def _dedupe_by_agent(votes: list[AgentVote]) -> list[AgentVote]:
    """F-22A: keep only the FIRST vote from each agent_id (anti-double-vote)."""
    seen: set[str] = set()
    out: list[AgentVote] = []
    for v in votes:
        if v.agent_id in seen:
            continue
        seen.add(v.agent_id)
        out.append(v)
    return out


# ── ConsensusResult ────────────────────────────────────────────────────────


class ConsensusResult(FrozenModel):
    """Immutable output of a consensus round.

    F-11A: risk_score == disagreement (1.0 - agreement_fraction); 1.0 on failure.
    F-11B: voter_breakdown (canonical_key → count) and dissenter_ids exposed.
    """

    protocol: ConsensusProtocol
    action: str | None = None
    action_hash: str = ""
    vote_count: int = Field(..., ge=0)
    agreement_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    authoritative: bool = False
    failed: bool = False
    failure_reason: str = ""
    requires_approval: bool = False
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    voter_breakdown: dict[str, int] = Field(default_factory=dict, max_length=100)
    dissenter_ids: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def _consistency(self) -> ConsensusResult:
        if self.failed and self.action is not None:
            raise ValueError("A failed ConsensusResult must not have an action")
        if not self.failed and self.action is None:
            raise ValueError("A successful ConsensusResult must have an action")
        return self


# ── Raft (F-21A: split-brain + follower-aware) ─────────────────────────────


def raft_consensus(
    votes: list[AgentVote],
    *,
    queen_authoritative: bool = True,
) -> ConsensusResult:
    """Authoritative-leader vote (Raft-inspired single-step).

    F-21A: detects split-brain (>1 queen vote) and folds follower agreement
           into the reported agreement_fraction.
    """
    if not votes:
        return ConsensusResult(
            protocol="raft",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
            risk_score=1.0,
        )

    votes = _dedupe_by_agent(votes)

    if queen_authoritative:
        queen_votes = [v for v in votes if v.agent_role == "queen"]

        # F-21A: split-brain detection
        if len(queen_votes) > 1:
            return ConsensusResult(
                protocol="raft",
                action=None,
                vote_count=len(votes),
                failed=True,
                failure_reason=f"Split-brain: {len(queen_votes)} queen votes",
                risk_score=1.0,
            )

        if queen_votes:
            winner = queen_votes[0]
            followers = [v for v in votes if v.agent_role != "queen"]
            if followers:
                winner_canon = canonicalize_action(winner.proposed_action)
                f_agree = sum(
                    1 for v in followers if canonicalize_action(v.proposed_action) == winner_canon
                ) / len(followers)
                # Average leader (1.0) + follower agreement
                agreement = (1.0 + f_agree) / 2
            else:
                agreement = 1.0

            buckets = _bucket_votes(votes)
            breakdown = {k: len(b) for k, b in buckets.items()}
            winner_canon = canonicalize_action(winner.proposed_action)
            dissenters = [
                v.agent_id for v in votes if canonicalize_action(v.proposed_action) != winner_canon
            ]

            return ConsensusResult(
                protocol="raft",
                action=winner.proposed_action,
                vote_count=len(votes),
                agreement_fraction=agreement,
                authoritative=True,
                voter_breakdown=breakdown,
                dissenter_ids=dissenters,
            )

    # Fallback: weighted majority (no queen present)
    return majority_consensus(votes)


# ── BFT (F-22A: textbook PBFT formula + n>=4 + dedupe) ─────────────────────


def bft_consensus(
    votes: list[AgentVote],
    *,
    quorum_fraction: float = 0.67,
) -> ConsensusResult:
    """Practical BFT: textbook formula `floor(2n/3) + 1` + n>=4 minimum."""
    # F-22C: defensive
    if quorum_fraction >= 1.0:
        raise ValueError("BFT quorum_fraction must be < 1.0 to tolerate Byzantine faults")

    if not votes:
        return ConsensusResult(
            protocol="bft",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
            risk_score=1.0,
        )

    votes = _dedupe_by_agent(votes)

    # F-22A: PBFT requires n >= 3f+1 with f >= 1 → n >= 4
    if len(votes) < 4:
        return ConsensusResult(
            protocol="bft",
            action=None,
            vote_count=len(votes),
            failed=True,
            failure_reason=(
                f"BFT requires >=4 unique voters to tolerate any Byzantine fault; got {len(votes)}"
            ),
            risk_score=1.0,
        )

    # Textbook PBFT threshold: floor(2n/3) + 1
    threshold = math.floor(2 * len(votes) / 3) + 1

    buckets = _bucket_votes(votes)
    breakdown = {k: len(b) for k, b in buckets.items()}

    # Find a bucket meeting the threshold
    for _canon_key, bucket in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        if len(bucket) >= threshold:
            action = _representative_action(bucket)
            agreement = len(bucket) / len(votes)
            winner_canon = canonicalize_action(action)
            dissenters = [
                v.agent_id for v in votes if canonicalize_action(v.proposed_action) != winner_canon
            ]
            return ConsensusResult(
                protocol="bft",
                action=action,
                vote_count=len(votes),
                agreement_fraction=agreement,
                authoritative=True,
                voter_breakdown=breakdown,
                dissenter_ids=dissenters,
            )

    # Quorum not reached
    best_canon, best_bucket = max(buckets.items(), key=lambda kv: len(kv[1]))
    best_action = _representative_action(best_bucket)
    return ConsensusResult(
        protocol="bft",
        action=None,
        vote_count=len(votes),
        agreement_fraction=len(best_bucket) / len(votes),
        authoritative=False,
        failed=True,
        failure_reason=(
            f"BFT quorum not reached: best bucket {best_action[:80]!r} got "
            f"{len(best_bucket)}/{len(votes)} (need {threshold})"
        ),
        voter_breakdown=breakdown,
        risk_score=1.0,
    )


# ── Gossip (F-23A: floor + min_voters; F-23B: count-based zero-conf) ──────


def gossip_consensus(
    votes: list[AgentVote],
    *,
    confidence_floor: float = 0.05,
    min_voters: int = 1,
) -> ConsensusResult:
    """Confidence-weighted single-round (LLM-adapted gossip).

    F-23A: confidence_floor prevents one high-conf vote from dominating
           a swarm of low-conf agreers.
    F-23B: zero-total-confidence path returns count-based agreement.
    """
    if not votes:
        return ConsensusResult(
            protocol="gossip",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
            risk_score=1.0,
        )

    votes = _dedupe_by_agent(votes)

    if len(votes) < min_voters:
        return ConsensusResult(
            protocol="gossip",
            action=None,
            vote_count=len(votes),
            failed=True,
            failure_reason=f"Gossip requires >={min_voters} voters; got {len(votes)}",
            risk_score=1.0,
        )

    buckets = _bucket_votes(votes)
    weighted: dict[str, float] = {}
    for canon_key, bucket in buckets.items():
        weighted[canon_key] = sum(max(confidence_floor, v.confidence) for v in bucket)

    breakdown = {k: len(b) for k, b in buckets.items()}
    total_weight = sum(weighted.values())

    if total_weight == 0.0:
        # F-23B: count-based fallback (was 0.0)
        best_canon = max(buckets, key=lambda k: len(buckets[k]))
        best_action = _representative_action(buckets[best_canon])
        return ConsensusResult(
            protocol="gossip",
            action=best_action,
            vote_count=len(votes),
            agreement_fraction=len(buckets[best_canon]) / len(votes),
            authoritative=False,
            voter_breakdown=breakdown,
        )

    best_canon = max(weighted, key=lambda k: weighted[k])
    best_action = _representative_action(buckets[best_canon])
    dissenters = [v.agent_id for v in votes if canonicalize_action(v.proposed_action) != best_canon]
    return ConsensusResult(
        protocol="gossip",
        action=best_action,
        vote_count=len(votes),
        agreement_fraction=weighted[best_canon] / total_weight,
        authoritative=False,
        voter_breakdown=breakdown,
        dissenter_ids=dissenters,
    )


# ── Majority (F-24A: first-proposer tie-break) ────────────────────────────


def majority_consensus(
    votes: list[AgentVote],
    *,
    min_fraction: float = 0.0,
) -> ConsensusResult:
    """Plurality with first-proposer tie-break (F-24A: was alphabetical)."""
    if not votes:
        return ConsensusResult(
            protocol="majority",
            action=None,
            vote_count=0,
            failed=True,
            failure_reason="No votes received",
            risk_score=1.0,
        )

    votes = _dedupe_by_agent(votes)
    buckets = _bucket_votes(votes)

    # F-24A: tie-break by earliest timestamp in the bucket
    earliest_ts: dict[str, float] = {k: min(v.timestamp for v in b) for k, b in buckets.items()}
    breakdown = {k: len(b) for k, b in buckets.items()}

    ranked = sorted(
        buckets.items(),
        key=lambda kv: (-len(kv[1]), earliest_ts[kv[0]]),
    )
    best_canon, best_bucket = ranked[0]
    best_action = _representative_action(best_bucket)
    fraction = len(best_bucket) / len(votes)

    if fraction < min_fraction:
        return ConsensusResult(
            protocol="majority",
            action=None,
            vote_count=len(votes),
            agreement_fraction=fraction,
            failed=True,
            failure_reason=(f"Best bucket got {fraction:.1%}, need >= {min_fraction:.0%}"),
            voter_breakdown=breakdown,
            risk_score=1.0,
        )

    dissenters = [v.agent_id for v in votes if canonicalize_action(v.proposed_action) != best_canon]
    return ConsensusResult(
        protocol="majority",
        action=best_action,
        vote_count=len(votes),
        agreement_fraction=fraction,
        authoritative=False,
        voter_breakdown=breakdown,
        dissenter_ids=dissenters,
    )


# ── Dispatch ───────────────────────────────────────────────────────────────


def run_consensus(
    votes: list[AgentVote],
    protocol: ConsensusProtocol,
    *,
    bft_quorum: float = 0.67,
    queen_authoritative: bool = True,
    risk_threshold: float = 0.8,
    min_voters: int = 1,
) -> ConsensusResult:
    """Route to the correct protocol; add risk + requires_approval metadata."""
    if protocol == "raft":
        result = raft_consensus(votes, queen_authoritative=queen_authoritative)
    elif protocol == "bft":
        result = bft_consensus(votes, quorum_fraction=bft_quorum)
    elif protocol == "gossip":
        result = gossip_consensus(votes)
    else:
        result = majority_consensus(votes)

    # F-11A: risk == disagreement
    risk = 1.0 - result.agreement_fraction if not result.failed else 1.0
    requires_approval = risk >= risk_threshold

    # F-17B: force HITL when below min_voters (except authoritative Raft)
    if (
        not result.failed
        and not (protocol == "raft" and result.authoritative)
        and result.vote_count < min_voters
    ):
        requires_approval = True
        risk = max(risk, 1.0)

    # Re-emit with risk metadata (frozen → model_dump + reconstruct)
    return ConsensusResult(
        **{
            **result.model_dump(),
            "risk_score": risk,
            "requires_approval": requires_approval,
        }
    )


__all__ = [
    "ConsensusResult",
    "canonicalize_action",
    "raft_consensus",
    "bft_consensus",
    "gossip_consensus",
    "majority_consensus",
    "run_consensus",
]
