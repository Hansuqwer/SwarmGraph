# Agent 06 — Base / Frozen Model Auditor
**Model:** Claude Opus 4.7
**Scope:** `hive-swarm/swarm/models/base.py`, `types.py`

## PURPOSE
Verify the foundation models (`HardenedModel`, `FrozenModel`) follow May-2026 Pydantic v2 best practice and that all `Literal` types are exhaustive.

## PUBLIC SURFACE (verified)
- `MUTABLE_CONFIG: ConfigDict` — `extra='forbid'`, `validate_assignment=True`, `use_enum_values=True`
- `FROZEN_CONFIG: ConfigDict` — `extra='forbid'`, `frozen=True`, `use_enum_values=True`
- `RESULT_CONFIG: ConfigDict` — `extra='forbid'`, `validate_assignment=False`, `use_enum_values=True`
- `stable_hash(text: str, length: int = 16) -> str`
- `now_ts() -> float`
- `class HardenedModel(BaseModel)` with `to_json_dict`, `from_json_dict`
- `class FrozenModel(BaseModel)`
- `Literal` aliases: `AgentRole`, `AgentStatus`, `TaskStatus`, `TaskPriority`, `SwarmTopology`, `ConsensusProtocol`, `SwarmStrategy`, `SwarmStatus`, `SwarmFailureCause`, `ComplexityTier`, `HistoryKind`

## WHAT WORKS ✅
- `MUTABLE_CONFIG` correctly composes the three required flags (`base.py:L18-L23`).
- `FROZEN_CONFIG` correctly composes `frozen=True` (`base.py:L26-L30`).
- `stable_hash` uses SHA-256 (cryptographically appropriate for objective_hash) (`base.py:L36`).
- `to_json_dict` uses `model_dump(mode='json')` — the Rust-fast path correctly chosen (`base.py:L52`).
- `from_json_dict` uses `model_validate` — correct round-trip (`base.py:L57`).
- Every consumer of these bases (`AgentSpec`, `AgentState`, `AgentVote`, `WorkerResult`, `SwarmTask`, `QueenDirective`, `SwarmConfig`, `ConsensusResult`, `SwarmMemoryEntry`, `SwarmMemory`, `SwarmState`, `SwarmCheckpoint`) inherits from one of them ✅.
- All 11 `Literal` aliases use lowercase string members consistent with `use_enum_values=True` ✅.

## WHAT'S BROKEN 🔴

### 06-T1 (med) — `MUTABLE_CONFIG` missing `revalidate_instances`
At `base.py:L18-L23`, `revalidate_instances` is not set. Default is `"never"`, meaning if a `SwarmState` is mutated through a non-validated path (e.g. someone bypasses `model_validate` and assigns to `__dict__`), stale invariants persist. Recommend `revalidate_instances="never"` explicitly (documents intent) or `"always"` for hot-reloaded configs.

### 06-T2 (low) — `RESULT_CONFIG` is unused in this codebase
Defined at `base.py:L33-L37` but no model imports it (verified via grep on `RESULT_CONFIG` — only in this file). Either:
- Apply it to `WorkerResult` and `ConsensusResult` (currently those use `FROZEN_CONFIG` because they're `FrozenModel` subclasses), or
- Remove it.

The fact that frozen results use `FROZEN_CONFIG` (rather than `RESULT_CONFIG`) is **fine** — frozen + `validate_assignment=False` are mutually consistent (you can't assign anyway). But the dead preset is confusing.

### 06-T3 (med) — `stable_hash` truncation to 16 chars (~64 bits)
`stable_hash(text, length=16)` truncates SHA-256 to 16 hex chars = 64 bits. Birthday collision probability becomes notable around 2^32 distinct objectives (~4 billion) — fine for swarm objective hashes, **NOT** fine if anyone reuses this for content-addressable storage. Add a docstring caveat. Currently used for `objective_hash`, `output_hash`, `result_hash`, `task_hash`, `entry_hash` — all stay safely below the threshold.

### 06-T4 (low) — `now_ts` uses `time.time()` (not monotonic)
`base.py:L40-L42`: `time.time()` is wall-clock; subject to NTP jumps. For `started_at`/`completed_at` math (`AgentState.duration_seconds`), this can produce **negative durations** during DST or NTP correction. Recommend `time.monotonic()` for duration math, keep `time.time()` for human-displayed timestamps.

## WHAT'S MISSING 🟡
- No `__init_subclass__` hook on `HardenedModel` to enforce a coverage policy ("no subclass may override `model_config` with `extra='allow'`").
- No `model_config = ConfigDict(strict=True)` anywhere — type coercion (`"30"` → `30`) is enabled by default. For trust-boundary models (state restored from disk), `strict=True` is the safer default.

## FIX RECOMMENDATION
```python
# base.py — recommended diff
MUTABLE_CONFIG = ConfigDict(
    extra="forbid",
    validate_assignment=True,
    use_enum_values=True,
    revalidate_instances="never",   # ← document intent (T1)
    strict=False,                   # ← document chosen permissive coercion
)

def stable_hash(text: str, length: int = 16) -> str:
    """SHA-256 hex prefix.
    NOTE: 16-char prefix = 64-bit collision space. Do NOT use for content-addressing."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]

def monotonic_ts() -> float:
    """For duration math; not wall-clock-comparable."""
    return time.monotonic()
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 06-T1 missing `revalidate_instances` | med | 5m |
| 06-T2 dead `RESULT_CONFIG` | low | 5m |
| 06-T3 hash truncation docstring | low | 10m |
| 06-T4 wall-clock duration math | med | 30m (add `monotonic_ts`, swap in `AgentState`) |
