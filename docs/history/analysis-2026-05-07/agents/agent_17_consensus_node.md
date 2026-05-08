# Agent 17 — Consensus Node Auditor
**Model:** Claude Opus 4.7
**Scope:** `hive-swarm/swarm/nodes/consensus.py`

## PURPOSE
Protocol dispatch + edge cases (1 vote, all-tie, all-abstain, single Byzantine voter).

## PUBLIC SURFACE (verified)
- `consensus_node(state) -> dict`
- `route_after_consensus(state) -> str` — `{approval_node, judge_node, end}`

## WHAT WORKS ✅
- Zero-vote case correctly transitions to failed via `swarm.fail("consensus_failed", ...)` (`consensus.py:L26-L31`) ✅.
- Reads protocol + risk_threshold from `swarm.config` — no hardcoded values (`consensus.py:L34-L40`) ✅.
- Clears `pending_votes = []` after consensus to prevent double-counting (`consensus.py:L43`) ✅.
- Routes to `awaiting_approval` when `requires_approval=True` (`consensus.py:L51-L53`) ✅.
- Records full consensus metadata in history (`consensus.py:L57-L63`) ✅.
- `route_after_consensus` covers all three return paths (failed → end, awaiting_approval → approval, else → judge) ✅.

## WHAT'S BROKEN 🔴

### 17-CORR1 (critical) — String-equality vote bucketing rejects semantically-equivalent outputs
The `Counter(v.proposed_action for v in votes)` pattern in every protocol (`models/consensus.py:L107, L141, L184, L194`) buckets votes by **exact string equality**.

Three coders returning:
```python
"def add(a,b): return a+b"
"def add(a, b):\n    return a+b"
"def add(a, b): return a + b"
```
each get **1 vote**. Consensus fails despite semantic agreement.

Fix: cluster by embedding similarity (cosine ≥ 0.9 = same cluster). When `VectorMemoryAdapter` is plugged in, reuse its `embed()`. Until then, normalise via AST hash (Python tasks) or whitespace-canonical form.

### 17-CORR2 (high) — `swarm.consensus_result = result` triggers `validate_assignment=True` ⇒ full SwarmState revalidation
`consensus.py:L42`. The freshly-built `ConsensusResult` triggers `_consistency` again on assignment, then the SwarmState's `_cap_lists`, `_agent_count_le_config`, `_auto_objective_hash` all re-run. Cost is ~28 fields per assignment ≈ 1ms. Over 50 iterations, 50ms wasted — fine. Flag for awareness.

### 17-LG1 (high) — `route_after_consensus` reads `swarm.status` to decide route, but the route also depends on `swarm.consensus_result.requires_approval`
`consensus.py:L67-L73`:
```python
def route_after_consensus(state):
    swarm = SwarmState.model_validate(state)
    if swarm.status == "failed": return "end"
    if swarm.status == "awaiting_approval": return "approval_node"
    return "judge_node"
```
The status is set by `consensus_node` based on `requires_approval`. So this is just a level of indirection. **OK for separation of concerns**, but if any other node sets `status="failed"` before the consensus edge fires, we route to end without checking why. Add a final `else` branch that logs the unexpected status.

### 17-OBS1 (med) — Failure history entry doesn't include the `failed=True` consensus_result
`consensus.py:L48-L50`. When consensus fails, only `swarm.fail(...)` is called — no entry like `swarm.append_history("consensus", {"protocol": ..., "failed": True, ...})`. The success path adds a rich entry; the failure path adds nothing. Inconsistent observability.

### 17-CORR3 (med) — Single-vote case: `majority_consensus` returns `agreement_fraction=1.0`
Per `models/consensus.py:L194-L201`, with 1 vote: `Counter` has 1 entry, count=1, total=1 → `agreement_fraction = 1.0`. Then `risk = 0.0` → no HITL even for genuinely risky single-agent decisions. **Recommend**: when `vote_count < min_voters`, force `requires_approval=True` regardless of agreement.

### 17-CORR4 (med) — All-abstain (all confidence=0) gossip path picks the most common action by string count
`models/consensus.py:L150-L162`. Already documented behaviour ✅. But `consensus_node` reports `agreement_fraction=0.0` to history — easy to misread as "consensus failed". Add a flag in history `kind` like `"consensus_zero_confidence"` to distinguish.

## WHAT'S MISSING 🟡
- No min-voters guard (single voter trivially "wins" Majority).
- No "split vote" detection (50/50 ties between two equally-popular actions).
- No `dissenter_ids` recorded — if 4/5 agree, who was the dissenter? (See `agent_11_consensus_models.md` recommendation.)
- No metric: consensus latency / vote-distribution distribution.

## FIX RECOMMENDATION
```python
# consensus.py — diff
def consensus_node(state):
    swarm = SwarmState.model_validate(state)
    if not swarm.pending_votes:
        swarm.fail("consensus_failed", "no votes received")
        swarm.append_history("consensus", {"outcome": "no_votes"})
        return swarm.to_json_dict()

    # NEW: min-voters guard
    if len(swarm.pending_votes) < 2 and swarm.config.consensus_protocol != "raft":
        # single voter is risky except for Raft (queen-authoritative)
        result = run_consensus(...)
        result = result.model_copy(update={"requires_approval": True, "risk_score": 1.0})
    else:
        result = run_consensus(...)

    swarm.consensus_result = result
    # ... (rest unchanged, but add failure-path history entry)
    if result.failed:
        swarm.append_history("consensus", {
            "protocol": result.protocol, "failed": True,
            "vote_count": result.vote_count,
            "reason": result.failure_reason,
        })
        swarm.fail("consensus_failed", result.failure_reason)
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 17-CORR1 string-eq bucketing | **critical** | 1wk (semantic clustering) |
| 17-CORR2 revalidation cost | low | n/a |
| 17-LG1 route fall-through log | low | 5m |
| 17-OBS1 failure history entry | med | 5m |
| 17-CORR3 single-vote risk | med | 15m |
| 17-CORR4 all-abstain visibility | low | 5m |
