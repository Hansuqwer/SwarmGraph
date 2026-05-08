# Agent 21 — Raft Protocol Auditor
**Model:** Claude Opus 4.7
**Scope:** `hive-swarm/swarm/models/consensus.py::raft_consensus`; gateway `consensus/strategies.py` (not fetched).

## PURPOSE
Leader election determinism, term monotonicity, log replication safety.

## EVIDENCE BASE
`hive-swarm/swarm/models/consensus.py:L48-L84` — `raft_consensus` body.

## WHAT WORKS ✅
- Empty-vote case → graceful failed result (`consensus.py:L57-L63`) ✅.
- "Queen-authoritative": if any vote has `agent_role == "queen"`, picks the queen vote with highest confidence (`consensus.py:L65-L75`) ✅ — implements Raft leader-decides semantics.
- Falls back to weighted majority when no queen present (`consensus.py:L77-L78`) ✅.
- Result has `authoritative=True` when leader-decided, distinguishing it from majority outcomes (`consensus.py:L72`) ✅.

## WHAT'S BROKEN 🔴

### 21-CORR1 (high) — This is NOT Raft; it's "leader-decides" with no log
Real Raft has: leader election (random timeouts), term monotonicity (every leader has a unique increasing term), log replication (followers append leader's entries in order), commit indices, snapshotting.

This implementation has **none** of those — it's effectively `if queen_vote: return queen_vote else: majority`. Document accurately as **"Authoritative Leader Vote"** (a Raft-inspired single-step) rather than Raft. This is OK for an LLM swarm (agents don't have long-running state), but the name is misleading.

### 21-CORR2 (med) — Multiple queen votes pick highest confidence — but Raft requires one leader at a time
`consensus.py:L67-L70`:
```python
queen_votes = [v for v in votes if v.agent_role == "queen"]
if queen_votes:
    winner = max(queen_votes, key=lambda v: v.confidence)
```
If two queens vote (e.g., due to a race), the winner is by confidence. Real Raft would consider this a split-brain. Either:
- Reject any consensus round with > 1 queen vote (`failed=True, failure_reason="split_brain"`), OR
- Document that highest-confidence wins as a deliberate simplification.

### 21-CORR3 (med) — `agreement_fraction = 1.0` always when queen wins
`consensus.py:L72`. Even if 4 of 5 non-queen agents disagreed, the queen's vote sets agreement to 1.0. That suppresses HITL trigger (`risk_score = 0.0` → no approval). This is a deliberate authoritative semantics choice, but for high-risk actions you'd want the queen vote to **lower** confidence when followers disagree. Recommend:
```python
follower_votes = [v for v in votes if v.agent_role != "queen"]
if follower_votes:
    follower_agreement = sum(1 for v in follower_votes if v.proposed_action == winner.proposed_action) / len(follower_votes)
    agreement = (1.0 + follower_agreement) / 2  # average leader (1.0) + follower agreement
else:
    agreement = 1.0
```

### 21-OBS1 (low) — `confidence` tie-breaking is non-deterministic when two queens have identical confidence
`max(... key=...)` picks the first encountered, which depends on vote arrival order. For determinism, sort by `(confidence, agent_id)`.

## WHAT'S MISSING 🟡
- No `term: int` on `AgentVote` — multi-round Raft impossible.
- No "log entry" abstraction — votes are one-shot.
- No leader liveness check (heartbeats) — irrelevant for one-shot decision but matters for long-running swarms.

## FIX RECOMMENDATION
```python
# consensus.py — diff
def raft_consensus(votes, *, queen_authoritative=True):
    if not votes:
        return ConsensusResult(protocol="raft", action=None, vote_count=0, failed=True, failure_reason="No votes")

    if queen_authoritative:
        queen_votes = [v for v in votes if v.agent_role == "queen"]
        if len(queen_votes) > 1:
            # split-brain detection
            return ConsensusResult(
                protocol="raft", action=None, vote_count=len(votes),
                failed=True, failure_reason=f"Split-brain: {len(queen_votes)} queens voted",
            )
        if queen_votes:
            winner = queen_votes[0]
            # Consider follower agreement for risk
            followers = [v for v in votes if v.agent_role != "queen"]
            if followers:
                f_agree = sum(1 for v in followers if v.proposed_action == winner.proposed_action) / len(followers)
                agreement = (1.0 + f_agree) / 2
            else:
                agreement = 1.0
            return ConsensusResult(
                protocol="raft", action=winner.proposed_action, vote_count=len(votes),
                agreement_fraction=agreement, authoritative=True,
            )
    return majority_consensus(votes)
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 21-CORR1 misnomer "Raft" | low | 30m (rename + doc) |
| 21-CORR2 split-brain | high | 15m |
| 21-CORR3 ignored follower disagreement | high | 30m |
| 21-OBS1 non-deterministic ties | low | 5m |
