# Agent 23 — Gossip Protocol Auditor
**Model:** Claude Sonnet 4.6
**Scope:** `hive-swarm/swarm/models/consensus.py::gossip_consensus`

## PURPOSE
Confidence weighting, convergence rounds, normalisation (Σw=1?).

## EVIDENCE BASE
`models/consensus.py:L135-L172` — `gossip_consensus` body.

## WHAT WORKS ✅
- Empty-vote graceful failure ✅ (`consensus.py:L143-L149`).
- Weighted dict via `defaultdict(float)` (`consensus.py:L151-L153`) — clean implementation.
- Zero-confidence fallback: when all votes have confidence=0, falls back to count-based selection (`consensus.py:L155-L162`) ✅ — never returns "no winner" if votes exist.
- `agreement_fraction = weighted[best_action] / total_weight` (`consensus.py:L165`) — correctly normalised to [0,1].
- `authoritative=False` (`consensus.py:L167`) ✅ — gossip is by definition eventually-consistent.

## WHAT'S BROKEN 🔴

### 23-CORR1 (med) — Single-round "gossip" is not gossip
True gossip protocols converge over **multiple rounds** of pairwise message exchange. This implementation runs **once** over a static `votes` list. It's effectively weighted majority. Same misnomer issue as Agent 21 flagged for Raft. Recommend renaming to `weighted_majority_consensus` or `confidence_weighted_consensus`.

### 23-CORR2 (high) — Σ confidences is NOT normalised to 1
`consensus.py:L154`: `total_weight = sum(weighted.values())`. With 5 voters each at confidence=1.0, total=5.0. With 5 voters each at 0.5, total=2.5. The `agreement_fraction` then varies wildly:
- 5 voters all agreeing on action A, all at confidence 1.0: weighted[A]=5.0, total=5.0 → agreement=1.0 ✅
- 5 voters: 4 agree on A at 0.5, 1 disagrees on B at 1.0: weighted[A]=2.0, weighted[B]=1.0, total=3.0 → agreement_for_A=0.667. Reasonable.
- 5 voters: 4 agree on A at 0.1, 1 disagrees on B at 1.0: weighted[A]=0.4, weighted[B]=1.0, total=1.4 → **best_action=B**, agreement=0.71.

The last case is dangerous: one high-confidence dissenter beats four low-confidence agreers. **Documented behaviour** (it's literally weighted voting) but it's worth flagging that calibration of agent confidence becomes critical. Recommend a sanity floor: `effective_confidence = max(0.1, v.confidence)` or `softmax`-style aggregation.

### 23-CORR3 (med) — No min-voter quorum
With 1 vote, `total_weight = confidence`, `weighted[action] = confidence`, `agreement = 1.0`. Single-voter "gossip" trivially succeeds. Add `min_voters=3` parameter.

### 23-OBS1 (low) — `agreement_fraction=0.0` for zero-confidence success path is misleading
`consensus.py:L160`: when all confidences are 0, fallback returns success with agreement=0.0. A consumer seeing `failed=False, agreement=0.0` might misread it as "no consensus". Recommend `agreement_fraction = best_count / len(votes)` (count-based) in that fallback.

## WHAT'S MISSING 🟡
- No multi-round simulation (real gossip).
- No agent-to-agent communication graph (every agent talks to every other agent in current model).
- No "convergence rounds" metric.
- No weighting by past Elo/trust score.

## FIX RECOMMENDATION
```python
# consensus.py — diff
def gossip_consensus(votes, *, min_voters: int = 3, confidence_floor: float = 0.05):
    if not votes:
        return ConsensusResult(protocol="gossip", action=None, vote_count=0, failed=True, failure_reason="No votes")
    if len(votes) < min_voters:
        return ConsensusResult(
            protocol="gossip", action=None, vote_count=len(votes),
            failed=True, failure_reason=f"Gossip requires >= {min_voters} voters; got {len(votes)}",
        )

    weighted = defaultdict(float)
    for v in votes:
        weighted[v.proposed_action] += max(confidence_floor, v.confidence)

    total_weight = sum(weighted.values())
    if total_weight == 0:
        counter = Counter(v.proposed_action for v in votes)
        best_action, best_count = counter.most_common(1)[0]
        return ConsensusResult(
            protocol="gossip", action=best_action, vote_count=len(votes),
            agreement_fraction=best_count / len(votes), authoritative=False,
        )

    best_action = max(weighted, key=weighted.get)
    return ConsensusResult(
        protocol="gossip", action=best_action, vote_count=len(votes),
        agreement_fraction=weighted[best_action] / total_weight, authoritative=False,
    )
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 23-CORR1 single-round gossip misnomer | low | 30m (rename) |
| 23-CORR2 high-conf dissenter wins | high | 30m (add floor) |
| 23-CORR3 no min-voter quorum | med | 5m |
| 23-OBS1 zero-conf agreement | low | 5m |
