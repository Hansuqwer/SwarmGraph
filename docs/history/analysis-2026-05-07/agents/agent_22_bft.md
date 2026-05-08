# Agent 22 — BFT Protocol Auditor
**Model:** Claude Opus 4.6
**Scope:** `hive-swarm/swarm/models/consensus.py::bft_consensus`

## PURPOSE
2/3 quorum math, Byzantine voter simulation, signature/commitment scheme (or absence thereof).

## EVIDENCE BASE
`models/consensus.py:L88-L131` — `bft_consensus` body.

## WHAT WORKS ✅
- Empty-vote graceful failure ✅ (`consensus.py:L97-L103`).
- `Counter.most_common()` pattern correctly counts identical action strings (`consensus.py:L108`).
- Returns `failed=True` with `failure_reason` containing the actual quorum miss numbers (`consensus.py:L121-L131`) — actionable diagnostics ✅.
- `authoritative=True` set only when quorum reached (`consensus.py:L116`).

## WHAT'S BROKEN 🔴

### 22-C1 (critical) — `math.ceil(n * q)` produces unanimity for n=3 with q=0.67
`consensus.py:L107`:
```python
threshold = math.ceil(len(votes) * quorum_fraction)
```
- n=3, q=0.67 → ceil(2.01) = **3** → requires unanimity → no Byzantine tolerance
- n=4, q=0.67 → ceil(2.68) = **3** → tolerates 1 fault ✅
- n=5, q=0.67 → ceil(3.35) = **4** → tolerates 1 fault ✅
- n=6, q=0.67 → ceil(4.02) = **5** → tolerates 1 fault ✅ (over-strict; PBFT would tolerate 1 with threshold 4)
- n=7, q=0.67 → ceil(4.69) = **5** → tolerates 2 faults ✅

Textbook PBFT: with `n = 3f+1` voters, tolerate up to `f` faults requiring `n - f = 2f+1` votes. So:
- n=4 (f=1): need 3 ✅
- n=7 (f=2): need 5 ✅
- For arbitrary n: `f = (n-1) // 3`, threshold = `n - f`

The current `ceil(n * q)` formula matches the textbook for n ≥ 4 by coincidence ✅. **The bug is only at n=3** where the formula demands unanimity. Recommended fix: switch to `floor(2*n/3) + 1` (the textbook formula), which gives:
- n=3 → 3 (still unanimity at n=3 because PBFT genuinely cannot tolerate any fault with only 3 voters; you need n ≥ 4 to tolerate f=1).

So actually the "bug" is not in the math — it's that **BFT with 3 voters cannot work**. Recommendation:
- Reject `len(votes) < 4` when `protocol == "bft"` with a clear failure reason.

### 22-SEC1 (critical) — Votes are unsigned; double-vote / replay possible
`AgentVote` (`models/agent.py:L91-L106`) has no `signature`, no `nonce`, no per-round identifier. A Byzantine "agent" can:
- Submit two votes with the same `agent_id` (no de-dupe in `bft_consensus`).
- Replay an old vote from a previous consensus round (no round_id binding).

Real PBFT relies on cryptographic signing + sequence numbers. Implementation gap captured in `agent_07_agent_models.md` (suggested `signature` + `nonce` fields).

### 22-CORR1 (high) — `bft_consensus` does not de-duplicate votes by `agent_id`
`consensus.py:L108`: `Counter(v.proposed_action for v in votes)` counts every vote, even from the same agent. Combined with 22-SEC1, a single Byzantine agent can stuff the ballot. Add:
```python
seen_agents = set()
unique_votes = []
for v in votes:
    if v.agent_id not in seen_agents:
        seen_agents.add(v.agent_id)
        unique_votes.append(v)
votes = unique_votes
```
in every protocol — not just BFT.

### 22-CORR2 (med) — `quorum_fraction=1.0` should be rejected at config (already is, but BFT here would pass)
The config validator (`models/config.py:L62-L70`) rejects `bft_quorum_fraction == 1.0` for BFT protocol ✅. But the function itself accepts 1.0. Defensive: assert `quorum_fraction < 1.0` inside `bft_consensus`.

### 22-OBS1 (low) — `failure_reason` contains "best action got X/Y votes" but does not name the action
For diagnostics, including the action preview helps: `f"... best action {best_action[:80]!r} got {best_count}/{n}"`.

## WHAT'S MISSING 🟡
- No round identifier (`round_id`) on votes.
- No vote signatures.
- No view-change protocol (PBFT needs this for liveness when leader is faulty).
- No "prepare → commit" two-phase commit.

## FIX RECOMMENDATION
```python
# consensus.py — diff
def bft_consensus(votes, *, quorum_fraction=0.67):
    if not votes:
        return ConsensusResult(protocol="bft", action=None, vote_count=0, failed=True, failure_reason="No votes")

    # NEW: de-dupe by agent_id
    seen, unique = set(), []
    for v in votes:
        if v.agent_id not in seen:
            seen.add(v.agent_id)
            unique.append(v)
    votes = unique

    # NEW: enforce minimum n for BFT semantics
    if len(votes) < 4:
        return ConsensusResult(
            protocol="bft", action=None, vote_count=len(votes),
            failed=True, failure_reason=f"BFT requires >=4 voters; got {len(votes)}",
        )

    threshold = math.floor(2 * len(votes) / 3) + 1   # textbook PBFT
    counter = Counter(v.proposed_action for v in votes)
    for action, count in counter.most_common():
        if count >= threshold:
            return ConsensusResult(
                protocol="bft", action=action, vote_count=len(votes),
                agreement_fraction=count / len(votes), authoritative=True,
            )
    best_action, best_count = counter.most_common(1)[0]
    return ConsensusResult(
        protocol="bft", action=None, vote_count=len(votes),
        agreement_fraction=best_count / len(votes), failed=True,
        failure_reason=(
            f"BFT quorum not reached: best action {best_action[:80]!r} got "
            f"{best_count}/{len(votes)} (need {threshold})"
        ),
    )
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 22-C1 unanimity at n=3 | **critical** | 30m |
| 22-SEC1 unsigned votes | **critical** | 1d (HMAC + nonce + key mgmt) |
| 22-CORR1 no agent de-dupe | high | 15m |
| 22-CORR2 q=1.0 sneaks past function | low | 5m |
| 22-OBS1 better failure message | low | 5m |
