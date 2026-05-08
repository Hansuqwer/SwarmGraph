# Agent 24 — Majority / CRDT Protocol Auditor
**Model:** Claude Sonnet 4.6
**Scope:** `hive-swarm/swarm/models/consensus.py::majority_consensus`; gateway `consensus/strategies.py` (not fetched).

## PURPOSE
Tie-break rule, abstain handling, idempotency.

## EVIDENCE BASE
`models/consensus.py:L177-L210` — `majority_consensus`.

## WHAT WORKS ✅
- Empty-vote graceful failure (`consensus.py:L186-L192`) ✅.
- Deterministic tie-break: `sorted(counter.items(), key=lambda x: (-x[1], x[0]))` — descending count, then ascending action string ✅ (`consensus.py:L195`).
- Always succeeds when ≥ 1 vote (`consensus.py:L194-L201`) ✅ — pure plurality.
- `authoritative=False` (`consensus.py:L201`) — correctly distinguishes from Raft.

## WHAT'S BROKEN 🔴

### 24-CORR1 (med) — Alphabetical tie-break biases toward action strings starting with `[A-...]`
Two equally-popular outputs:
- `"Apply patch foo"` → wins
- `"Zap that bug"` → loses

Even though both have N votes. Arbitrary first-letter bias. Better tie-break:
1. **First-proposer-wins**: pick the action whose earliest-timestamp vote is oldest.
2. **Highest-summed-confidence**: pick the action with highest `Σ confidence`.
3. **Random with seed**: deterministic but not first-letter-biased.

### 24-CORR2 (low) — No idempotency test, but the function IS idempotent
`majority_consensus(votes)` is a pure function over `votes`. Calling it twice yields identical results ✅. Worth a property-based test (Agent 04, finding 04-T1).

### 24-CORR3 (low) — Plurality with no threshold can return a "winner" with 1 vote out of 100
If 100 voters all give different actions, the first alphabetically wins with 1/100 = 1% agreement. `risk_score` becomes `1 - 0.01 = 0.99` → triggers HITL ✅. So the safety net works, but the "winner" is misleading. Document.

## WHAT'S MISSING 🟡
- No "abstain" support — `proposed_action="abstain"` is treated as a regular string.
- No quorum threshold (e.g. require ≥ 50% to win).
- No CRDT semantics — title mentions CRDT but implementation is plain majority. **Misnomer**.

## FIX RECOMMENDATION
```python
# consensus.py — diff
def majority_consensus(votes, *, min_fraction: float = 0.0):
    if not votes:
        return ConsensusResult(protocol="majority", action=None, vote_count=0, failed=True, failure_reason="No votes")

    # First-proposer tie-break: track earliest timestamp per action
    earliest_ts = {}
    counter = Counter()
    for v in votes:
        counter[v.proposed_action] += 1
        if v.proposed_action not in earliest_ts:
            earliest_ts[v.proposed_action] = v.timestamp

    # Sort by (-count, earliest_ts) — first proposer wins ties
    ranked = sorted(counter.items(), key=lambda x: (-x[1], earliest_ts[x[0]]))
    best_action, best_count = ranked[0]
    fraction = best_count / len(votes)

    if fraction < min_fraction:
        return ConsensusResult(
            protocol="majority", action=None, vote_count=len(votes),
            agreement_fraction=fraction, failed=True,
            failure_reason=f"Best action got {fraction:.1%}, need ≥ {min_fraction:.0%}",
        )

    return ConsensusResult(
        protocol="majority", action=best_action, vote_count=len(votes),
        agreement_fraction=fraction, authoritative=False,
    )
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 24-CORR1 alphabetical bias | med | 15m |
| 24-CORR2 no idempotency test | low | 1h (Hypothesis) |
| 24-CORR3 1/100 winner | low | 5m (doc) |
| Missing CRDT semantics or rename | med | 30m |
