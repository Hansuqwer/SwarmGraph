# Agent 09 — State Machine Auditor
**Model:** Claude Opus 4.6
**Scope:** `hive-swarm/swarm/models/state.py`, `ai-coder-hardening-improved/.../workflow/state.py`
**Deliverable goal:** `SwarmState` / `WorkflowState` JSON round-trip, list caps, `objective_hash` validator, `repo_root` validation, **C1/C7/C8 verification**.

## PURPOSE
The two `*State` models are the LangGraph state-machine cores. Every audit invariant funnels through them.

## PUBLIC SURFACE (verified)
**`SwarmState(HardenedModel)`** — 28 fields (identity, config, agents, tasks, routing, consensus, worker_results, memory, sona, status, history, errors, timestamps).
**`SwarmCheckpoint(HardenedModel)`** — serializable snapshot.
**`WorkflowState(BaseModel)`** with `ConfigDict(extra='forbid', validate_assignment=True)` ✅ — hardened per C1.

## WHAT WORKS ✅

### `SwarmState` (`hive-swarm/swarm/models/state.py`)
- `extra='forbid', validate_assignment=True` via `HardenedModel` ✅ (`base.py:L18`).
- `_auto_objective_hash` model_validator computes `stable_hash(self.objective)` automatically when blank (`state.py:L107-L112`) ✅.
- `_cap_lists` model_validator enforces `_MAX_HISTORY=500` and `_MAX_ERRORS=100` (`state.py:L114-L121`) ✅.
- `_agent_count_le_config` cross-field invariant (`state.py:L123-L131`) ✅.
- `agents`, `errors`, `worker_results`, `pending_votes`, `completed_task_ids` all use **functional update** (`= ... + [x]`) — works correctly with `validate_assignment=True` ✅.
- `to_json_dict()` / `from_json_dict()` correctly use `mode='json'` and `model_validate` (`state.py:L210-L218`) ✅.
- `check_drift()` is a clean keyword-overlap heuristic with documented limitations (`state.py:L143-L155`) — not perfect but explicit.

### `WorkflowState` (`ai-coder-hardening-improved/.../workflow/state.py`)
- **C1 confirmed fixed**: `model_config = ConfigDict(extra="forbid", validate_assignment=True)` at `state.py:L121-L124` ✅.
- **C6 confirmed fixed**: `TokenUsage.input_tokens / output_tokens` have `Field(default=0, ge=0)` at `state.py:L113-L114` ✅.
- **C7 confirmed fixed**: `_cap_lists` model_validator caps `history`, `errors`, `model_errors` at `state.py:L172-L182` ✅.
- **C8 confirmed fixed**: `repo_root` field_validator rejects empty + `..` traversal at `state.py:L141-L150` ✅.
- **C10 confirmed fixed**: `HistoryEntry` discriminated union over 6 typed variants at `state.py:L60-L100` ✅.

## WHAT'S BROKEN 🔴

### 09-CORR1 (high) — `_cap_lists` truncates `errors` from the front, but `errors` are typically appended chronologically
`state.py:L120` does `self.errors[-_MAX_ERRORS:]` — keeps the **last** 100 errors. That's correct for "most recent failures matter most". But `history` does `self.history[:1] + self.history[-(_MAX_HISTORY-1):]` — keeps first + last (preserving the swarm_init entry). **Mismatch in policy** between the two lists. Either document why or unify.

### 09-T1 (med) — `_cap_lists` runs on **every** revalidation, not just construction
With `validate_assignment=True`, every assignment to any field triggers all `model_validator(mode="after")`s. `_cap_lists` slicing 500-element lists every time you set `swarm.iteration += 1` is **O(n) per attribute set**. With ~50 history events per swarm run, that's 50 × O(500) = 25k extra ops. Negligible at current scale, but worth a `if len(...) > MAX:` guard outside the slice (already there in `_cap_lists` on `errors` ✅, but the `history` branch always slices).

### 09-CORR2 (med) — `assert_no_drift` raises but state mutation already happened
`state.py:L157-L165`:
```python
def assert_no_drift(self, candidate_output: str) -> None:
    if not self.check_drift(candidate_output):
        self.status = "drifted"
        self.failure_cause = "objective_drift"
        raise ValueError(...)
```
With `validate_assignment=True`, `self.status = "drifted"` triggers `_auto_objective_hash` and `_cap_lists` revalidation BEFORE the raise. If those validators fail (e.g. agents list grew above max during the same node), the raise hides behind a different `ValidationError`. Defensive: do the raise first, then mutate.

### 09-OBS1 (med) — `add_error` appends but does NOT call `touch()`
`state.py:L173-L174`. Updated_at stays stale after errors. Minor observability bug.

### 09-CORR3 (med) — `mark_task_complete` looks up by linear scan
`state.py:L198-L204`. With ~100 tasks (max_agents cap), this is O(n). Fine. But `validate_assignment=True` means the assignment `task.complete(result)` re-validates **the whole `tasks` list** through the parent — full-list revalidation per completion. Use `model_copy(update={...})` or build an index.

### 09-CORR4 (low) — `SwarmCheckpoint.state_snapshot: dict[str, Any]` is **not** typed
The snapshot is a dict; restoring it round-trips back through `SwarmState.from_json_dict` ✅, but the field type loses all info. Consider `SwarmCheckpoint` becoming generic on the state type, or at least documenting the shape.

### 09-OBS2 (low) — `SwarmStatus` includes `"drifted"` but `failure_cause: SwarmFailureCause | None` doesn't include `"drifted"`-mapping cause
`types.py:L43, L57`: status `"drifted"` correlates with cause `"objective_drift"`. The mismatch is fine but a typed `dict[SwarmStatus, SwarmFailureCause]` map would catch incorrect pairings.

## WHAT'S MISSING 🟡
- No `from __future__ import annotations` lifecycle test for `SwarmState` round-trip with all 28 fields populated.
- No version field on `SwarmState` — schema migrations will be painful.
- `WorkflowState` has no `objective_hash` field analogous to `SwarmState.objective_hash` — only `prompt_hash` (per-call). Cross-project anti-drift would need this.

## FIX RECOMMENDATION
```python
# state.py — diff
def assert_no_drift(self, candidate_output: str) -> None:
    if not self.check_drift(candidate_output):
        # raise FIRST, mutate second (pattern: invariant before mutation)
        msg = f"Anti-drift violation: output does not satisfy objective (hash={self.objective_hash})"
        self.status = "drifted"        # noqa: still mutate for caller introspection
        self.failure_cause = "objective_drift"
        raise ValueError(msg)

def add_error(self, msg: str) -> None:
    self.errors = (self.errors + [msg])[-_MAX_ERRORS:]
    self.touch()    # ← add
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 09-CORR1 inconsistent cap policy | med | 30m |
| 09-T1 slice-on-every-assignment | low | 30m |
| 09-CORR2 mutate-before-raise | med | 10m |
| 09-OBS1 missing touch | low | 1m |
| 09-CORR3 O(n) revalidation on task complete | med | 1d (refactor) |
| 09-CORR4 untyped snapshot | low | 1h |
| Missing schema version | high | 1h |

**Verdict:** C1 / C6 / C7 / C8 / C10 from `ANALYSIS_AND_REVIEW.md` are **all confirmed fixed** in `ai-coder-hardening-improved`. The same hardening should be back-ported to `hive-swarm/swarm/models/state.py` for items not yet done (notably: schema version field, dual `objective_hash`).
