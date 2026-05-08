# Agent 10 — Config Auditor
**Model:** Claude Sonnet 4.6
**Scope:** `hive-swarm/swarm/models/config.py`; gateway `models/state.py`, `quota.py`, `credentials.py`

## PURPOSE
Verify `frozen=True`, threshold ordering, BFT quorum invariants.

## PUBLIC SURFACE (verified)
- `class SwarmConfig(FrozenModel)` — 18 fields, all bounded, with 2 cross-field validators.
- `complexity_tier(score: float) -> str` — `tier1_fast`/`tier2_medium`/`tier3_swarm` mapping.

## WHAT WORKS ✅
- `SwarmConfig` is `FrozenModel` ✅ (`config.py:L11`).
- Every numeric field has `ge=...` and `le=...` bounds (`config.py:L20-L48`):
  - `max_agents: ge=1, le=100` ✅
  - `bft_quorum_fraction: ge=0.51, le=1.0` ✅
  - `tier1_threshold, tier2_threshold ∈ [0.0, 1.0]` ✅
  - `memory_max_entries: ge=10, le=100_000` ✅
  - `sona_min_confidence ∈ [0.0, 1.0]` ✅
  - `require_approval_above_risk ∈ [0.0, 1.0]` ✅
  - `max_iterations: ge=1, le=50` ✅
- `_tiers_must_be_ordered` model_validator enforces `tier1 < tier2` (`config.py:L51-L60`) ✅.
- `_bft_quorum_reasonable` rejects `bft_quorum_fraction == 1.0` when protocol is "bft" (`config.py:L62-L70`) ✅ — preserves fault tolerance.
- `complexity_tier()` returns the correct tier based on the configured thresholds (`config.py:L72-L78`) ✅.

## WHAT'S BROKEN 🔴

### 10-CORR1 (high) — `bft_quorum_fraction = 0.51` is permitted but breaks PBFT semantics
`config.py:L24`: `Field(default=0.67, ge=0.51, le=1.0)`. PBFT requires **strict supermajority** (> 2/3 = 0.667) to tolerate `f` Byzantine voters out of `3f+1`. A user who configures `bft_quorum_fraction=0.51` gets a "BFT" protocol that's actually plain majority. Either:
- Tighten the lower bound to `0.667`, or
- Document this as `quorum_fraction` (general parameter) rather than `bft_quorum_fraction` (BFT-specific).

### 10-CORR2 (med) — `tier1_threshold = tier2_threshold` is rejected, but **strictly** less is required only at construction
With `frozen=True` the rejection is permanent ✅. But the validator uses `>=` (correct, strict). However the **default** `tier1=0.15`, `tier2=0.50` leaves a wide gap — that's fine; just noting that `tier1=0.5, tier2=0.5` would correctly be rejected.

### 10-T1 (low) — `memory_namespace: min_length=1, max_length=64` allows shell-meta chars
`config.py:L36`. Memory namespaces feed into file paths in `FileCheckpointStore` (verified: `directory / f"cp-{state.swarm_id}-..."` — uses `swarm_id` not `memory_namespace`, so OK). But if a future backend uses `memory_namespace` as a file/key prefix, `../`-injection becomes possible. Add a charset validator (alnum + `_-`).

### 10-DOC1 (low) — `raft_queen_authoritative: bool = True` is documented as Raft-specific but used in `run_consensus` regardless of protocol
`models/consensus.py:L209` calls `run_consensus(..., queen_authoritative=swarm.config.raft_queen_authoritative)` and only the Raft branch consumes it (verified at `consensus.py:L60`). The dispatch ignores it for BFT/Gossip/Majority ✅. So the param is correctly Raft-specific in effect — but the codename + only-used-by-one-protocol is brittle. Add a docstring.

### 10-CORR3 (low) — `checkpoint_every_n_tasks` not enforced anywhere
`config.py:L29`: `Field(default=1, ge=1, le=100)`. grep shows **no consumer** of this field. Either implement (in `nodes/checkpointing.py`'s save loop) or remove.

## Gateway models not fetched in this run
We did NOT fetch `ai-provider-swarm-gateway/.../models/state.py`, `quota.py`, `credentials.py`, so cannot confirm the same hardening there. **Recommend Agent 10 re-runs against those three files** to confirm:
- `GatewayState` is `extra='forbid', validate_assignment=True`
- `QuotaUsage` has `ge=0` on `used_requests`, `used_tokens`
- `ProviderCredentialRef` only stores **env-var name strings**, not actual secrets

(Agent 29 partially covers this from the consumer side — see `agent_29_providers.md`.)

## WHAT'S MISSING 🟡
- No `SwarmConfig.from_yaml(path)` / `.from_env(...)` factory.
- No schema-version field on `SwarmConfig`.
- No `__hash__` / `__eq__` test (frozen models should support both — Pydantic v2 gives them automatically with `frozen=True` ✅).

## FIX RECOMMENDATION
```python
# config.py — diff
bft_quorum_fraction: float = Field(default=0.67, ge=0.667, le=1.0)   # tighten

memory_namespace: str = Field(
    default="default",
    min_length=1,
    max_length=64,
    pattern=r"^[a-zA-Z0-9_\-]+$",     # add
)

raft_queen_authoritative: bool = Field(
    default=True,
    description=(
        "Only consumed by Raft consensus dispatch in run_consensus(). "
        "Has no effect when consensus_protocol != 'raft'."
    ),
)
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 10-CORR1 BFT quorum lower bound | high | 5m |
| 10-T1 namespace charset | low | 5m |
| 10-DOC1 raft_queen_auth docstring | low | 5m |
| 10-CORR3 unused config | low | 1h (implement) or 5m (remove) |
| Gateway config re-audit | high | 30m (re-fetch) |
