# Agent 11 — Consensus Model Auditor
**Model:** Claude Opus 4.7
**Scope:** `hive-swarm/swarm/models/consensus.py` — `ConsensusResult` schema only (protocol-impl audited by 21–24).

## PURPOSE
Audit the result-schema and the dispatch wrapper.

## PUBLIC SURFACE (verified)
- `class ConsensusResult(FrozenModel)` — 11 fields.
- `raft_consensus(votes, *, queen_authoritative)`
- `bft_consensus(votes, *, quorum_fraction)`
- `gossip_consensus(votes)`
- `majority_consensus(votes)`
- `run_consensus(votes, protocol, *, bft_quorum, queen_authoritative, risk_threshold)` — dispatcher.

## WHAT WORKS ✅
- `ConsensusResult` is `FrozenModel` ✅ (`consensus.py:L21`).
- All numeric fields bounded: `vote_count ge=0`, `agreement_fraction ∈ [0,1]`, `risk_score ∈ [0,1]` (`consensus.py:L25-L34`).
- `_consistency` model_validator enforces `failed ⇒ action is None` AND `not failed ⇒ action is not None` (`consensus.py:L36-L41`) ✅ — strong invariant.
- Every protocol returns a `ConsensusResult` even for empty votes (no `None`, no exception) ✅ — graceful degradation.
- `run_consensus` re-wraps the inner result with `risk_score` and `requires_approval` (`consensus.py:L218-L226`) ✅.

## WHAT'S BROKEN 🔴

### 11-CORR1 (high) — `run_consensus` silently re-validates a frozen model via `model_dump + new instance`
`consensus.py:L218-L226`:
```python
return ConsensusResult(
    **{
        **result.model_dump(),
        "risk_score": risk,
        "requires_approval": requires_approval,
    }
)
```
This is the correct pattern for "update a frozen model" ✅, BUT `model_dump()` (no `mode="json"`) returns Python types — for `FrozenModel` with `use_enum_values=True`, this is OK since `ConsensusProtocol` is a Literal not an Enum. **Verified safe** for current types. Flag only if any field becomes an actual Enum.

### 11-CORR2 (high) — Risk score is `1.0 - agreement_fraction` even when `failed=True`
`consensus.py:L214`:
```python
risk = 1.0 - result.agreement_fraction if not result.failed else 1.0
```
Correctly forces `risk=1.0` on failure ✅. But on `not failed`, `agreement_fraction=0.51` → `risk=0.49`. With default `require_approval_above_risk=0.8`, that means **only consensus rounds with < 20% agreement trigger HITL**. That's an unusually-loose policy — most production swarm setups want HITL for `agreement < 0.7`. Recommend either:
- Re-define `risk = 1.0 - agreement_fraction` with comment that risk is "disagreement", OR
- Change to `risk = 1.0 - (max_action_count / vote_count)` (same thing, clearer).

The bug is **conceptual / doc**: the threshold semantics aren't what most users expect. Document explicitly.

### 11-T1 (low) — `metadata: dict[str, Any]` is unbounded
`consensus.py:L34`. Anyone can shove a 10MB blob into a frozen result. Cap it.

### 11-CORR3 (med) — `_consistency` validator allows `agreement_fraction=0.0` on a successful result
At `consensus.py:L33`, `agreement_fraction` defaults to 0.0. The `gossip_consensus` zero-confidence fallback (`consensus.py:L150-L162`) returns a successful result with `agreement_fraction=0.0`. Then `run_consensus` computes `risk=1.0` → triggers HITL. That's **correct behaviour** but counter-intuitive: a "successful" consensus with risk=1.0. Document it.

## WHAT'S MISSING 🟡
- No `ConsensusResult.voter_breakdown: dict[str, int]` showing per-action vote counts (would help debugging).
- No `ConsensusResult.dissenters: list[str]` (agent_ids that disagreed) — useful for HITL UI.
- No serialisation of the `votes` themselves into the result (audit trail).

## FIX RECOMMENDATION
```python
# consensus.py — diff
class ConsensusResult(FrozenModel):
    ...
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=64)  # cap
    voter_breakdown: dict[str, int] = Field(default_factory=dict, max_length=100)  # add
    dissenter_ids: list[str] = Field(default_factory=list, max_length=100)         # add
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 11-CORR2 risk semantics doc | med | 10m |
| 11-T1 metadata cap | low | 5m |
| 11-CORR3 zero-confidence success doc | low | 5m |
| Missing voter_breakdown / dissenters | high | 1h |
