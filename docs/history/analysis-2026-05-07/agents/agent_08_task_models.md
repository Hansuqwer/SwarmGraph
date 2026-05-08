# Agent 08 — Task & Directive Auditor
**Model:** Claude Sonnet 4.6
**Scope:** `hive-swarm/swarm/models/task.py`

## PURPOSE
Audit `SwarmTask` and `QueenDirective` schemas, lifecycle invariants, hash stability.

## PUBLIC SURFACE (verified)
- `class SwarmTask(HardenedModel)` — atomic unit of work with lifecycle: `pending → assigned → running → completed | failed | cancelled`
- `class QueenDirective(FrozenModel)` — immutable instruction issued from queen to one worker

## WHAT WORKS ✅
- Field bounds: `task_id min/max 1/64`, `description min/max 1/4096` (`task.py:L20-L22`).
- Self-dep dedupe: `_no_self_dep` validator deduplicates `depends_on` while preserving order (`task.py:L51-L54`).
- `attempts: int = Field(ge=0, le=10)` — bounded retries (`task.py:L40`).
- `priority_value()` exposes a numeric priority for heap-ordering (`task.py:L99-L101`).
- `is_ready(completed_task_ids)` correctly checks all `depends_on` are complete (`task.py:L93-L95`).
- Lifecycle helpers (`assign`, `start`, `complete`, `fail`, `cancel`) raise `ValueError` on illegal transitions (`task.py:L65-L91`) ✅.
- `QueenDirective._task_must_be_assigned` model_validator ensures the embedded task is in an active state (`task.py:L121-L127`) ✅.

## WHAT'S BROKEN 🔴

### 08-CORR1 (med) — `_no_self_dep` validator does NOT actually check for self-dependency
At `task.py:L51-L54`:
```python
@field_validator("depends_on")
@classmethod
def _no_self_dep(cls, v: list[str]) -> list[str]:
    return list(dict.fromkeys(v))   # only deduplicates!
```
The function name promises "no self-dep" but the body just deduplicates. A task with `task_id="t1"` can still have `depends_on=["t1"]`, which would deadlock. Two fixes possible:
- Rename to `_dedupe_dep` (truth in advertising), AND
- Add a `model_validator(mode="after")` that checks `self.task_id not in self.depends_on`.

### 08-CORR2 (med) — No cycle detection in `depends_on`
There is no validator catching `t1 → t2 → t1` cycles. In current call sites (queen creates linear sub-tasks), this is unreachable, but if a future feature lets users construct DAGs, infinite recursion in `is_ready` traversal is possible. Add a topological-sort validator at directive-issue time.

### 08-T1 (low) — `result_hash` recomputed only when `result_summary` changes via `complete()`
At `task.py:L60-L63` the `_compute_result_hash` model_validator only recomputes when `result_summary and not result_hash`. If a caller sets `task.result_summary = "new"` (via `validate_assignment=True`), the validator re-fires — but only sets the hash if it was empty. Result: stale hash. Fix: always recompute.

### 08-CORR3 (low) — `task.fail("")` collapses to ambiguous state
`task.py:L82-L85`:
```python
def fail(self, reason: str = "") -> None:
    self.status = "failed"
    self.result_summary = reason
    self.completed_at = now_ts()
```
If reason is `""`, `result_summary` becomes `""`, indistinguishable from a default `pending` task. Reject empty reason.

## WHAT'S MISSING 🟡
- No `SwarmTask.deadline: float | None` — for tier-1 fast-path SLOs.
- No `SwarmTask.retry_after: float | None` — for backoff scheduling.
- `QueenDirective` has no `expires_at` — a directive sitting in a delayed Send queue could be stale.

## FIX RECOMMENDATION
```python
# task.py — diff
@field_validator("depends_on")
@classmethod
def _dedupe_dep(cls, v: list[str]) -> list[str]:    # renamed
    return list(dict.fromkeys(v))

@model_validator(mode="after")
def _no_self_dependency(self) -> "SwarmTask":
    if self.task_id in self.depends_on:
        raise ValueError(f"task {self.task_id!r} cannot depend on itself")
    return self

@model_validator(mode="after")
def _refresh_result_hash(self) -> "SwarmTask":
    if self.result_summary:
        self.result_hash = stable_hash(self.result_summary)
    else:
        self.result_hash = ""
    return self

def fail(self, reason: str) -> None:
    if not reason.strip():
        raise ValueError("fail() requires a non-empty reason")
    self.status = "failed"
    self.result_summary = reason
    self.completed_at = now_ts()
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 08-CORR1 self-dep validator misnamed | med | 5m |
| 08-CORR2 no cycle detection | low | 1h (toposort) |
| 08-T1 stale `result_hash` | low | 5m |
| 08-CORR3 empty fail reason | low | 5m |
