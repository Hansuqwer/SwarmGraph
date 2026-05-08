# Agent 16 — Worker Node Auditor
**Model:** Claude Sonnet 4.6
**Scope:** `hive-swarm/swarm/nodes/worker.py`

## PURPOSE
`collect_results` aggregation, partial-failure handling, deterministic ordering.

## PUBLIC SURFACE (verified)
- 9 `_execute_*` role behaviours (researcher, architect, coder, tester, reviewer, security, optimizer, coordinator, default).
- `_ROLE_DISPATCH: dict[AgentRole, Callable]`
- `worker_node(agent_state_dict) -> dict`
- `_estimate_confidence(output, task_desc) -> float`
- `collect_results_node(state) -> dict`

## WHAT WORKS ✅
- Pure-function role handlers — no side effects, fully testable (`worker.py:L17-L52`).
- `_ROLE_DISPATCH` covers every `AgentRole` literal except `documenter` (mapped to default ✅) (`worker.py:L54-L65`).
- `worker_node` calls `agent_state.mark_started()` then `mark_done` / `mark_failed` based on outcome (`worker.py:L75, L84, L93`) ✅.
- `try / except Exception` wraps the executor — never crashes the graph (`worker.py:L80-L98`) ✅.
- Returns `{"_worker_result": ..., "_agent_id": ...}` — a stable, parseable shape.
- `_estimate_confidence` clamps to `[0, 1]` and degrades gracefully on empty output (`worker.py:L113-L122`) ✅.
- `collect_results_node` converts every `WorkerResult` to a vote via `to_vote()` (`worker.py:L131-L132`) ✅ — leverages the typed converter.

## WHAT'S BROKEN 🔴

### 16-LG1 (critical) — Worker returns `{"_worker_result": ..., "_agent_id": ...}` but `collect_results_node` reads `swarm.worker_results`
`worker.py:L100-L103`:
```python
return {
    "_worker_result": result.model_dump(mode="json"),
    "_agent_id": agent_state.agent_id,
}
```
The keys `_worker_result` and `_agent_id` are **never read** by `collect_results_node` (`worker.py:L131-L139`). `collect_results_node` reads `swarm.worker_results` — which the workers never write to.

In LangGraph, when a node returns a dict, those keys merge into the graph state. So `_worker_result` ends up in the state's `_worker_result` key — but `_worker_result` is **not a field on `SwarmState`**, and `SwarmState` has `extra='forbid'` ⇒ the next `SwarmState.model_validate(state)` (in `collect_results_node`) **raises ValidationError**.

This is the same latent bug Agent 13 flagged (13-T1). Two fixes possible:
1. Worker returns `{"worker_results": [result.model_dump(mode="json")]}` AND register an `Annotated[list, operator.add]` reducer on `SwarmState.worker_results`.
2. Use a custom reducer in `StateGraph(..., state_schema=...)`.

The mock graph manually appends to `worker_results` (`factory.py:L150-L154`) so tests pass, **hiding the bug from any test that doesn't run real LangGraph**.

### 16-CORR1 (high) — `_estimate_confidence` token overlap is asymmetric
`worker.py:L113-L122`:
```python
task_tokens = set(task_desc.lower().split()[:20])
out_tokens = set(output.lower().split())
overlap = len(task_tokens & out_tokens) / max(len(task_tokens), 1)
```
Truncating `task_tokens` to first 20 words means a long task description has its tail ignored — confidence is overestimated for a worker that ignores the tail. Use `min(len(task_tokens), len(out_tokens))` denominator (Jaccard-like), or tokenise both equally.

### 16-CORR2 (med) — Stub outputs include `task_desc[:100]` which can leak secrets
`worker.py:L17-L52`. If a task description contains an API key (it shouldn't, but), the worker output contains the first 100 chars — which then enters `output_hash`, `latest_output`, `final_output`, and the checkpoint. The `SwarmRedactingCheckpointer` redacts on write, but the in-memory state retains it. Add a redaction pass before `mark_done`.

### 16-LG2 (med) — `worker_node` does NOT update `swarm.tasks[i].status`
The worker marks **its own** `AgentState` as done/failed but never reflects back to the parent `SwarmTask` (`task_id` exists in the directive but isn't written to). After `collect_results_node`, the swarm sees no task as completed. Either:
- Have `collect_results_node` iterate over `worker_results` and call `swarm.mark_task_complete(task_id, output)`.
- Or have `worker_node` return both a result AND a task-status update via reducer.

### 16-OBS1 (low) — `_ROLE_DISPATCH["queen"] = _execute_coordinator`
`worker.py:L62`. A queen role mapped to coordinator behaviour — fine, but worth a comment because it's surprising.

## WHAT'S MISSING 🟡
- No timeout on `executor(...)` call.
- No retries / circuit breaker for transient model errors (when LLM gateway is integrated).
- No metrics on worker duration distribution.

## FIX RECOMMENDATION
```python
# worker.py — diff
import operator
from typing import Annotated

# In SwarmState (state.py), change:
worker_results: Annotated[list[WorkerResult], operator.add] = Field(default_factory=list)

# In worker_node, return:
return {
    "worker_results": [result],   # operator.add merges across parallel Sends
}

def _estimate_confidence(output: str, task_desc: str) -> float:
    if not output.strip():
        return 0.0
    task_tokens = set(task_desc.lower().split())   # no truncation
    out_tokens = set(output.lower().split())
    union = task_tokens | out_tokens
    overlap = len(task_tokens & out_tokens) / max(len(union), 1)  # Jaccard
    length_score = min(len(output) / 500.0, 0.5)
    return round(min(1.0, overlap * 0.5 + length_score), 3)

# In collect_results_node, after collecting votes:
for r in swarm.worker_results:
    if r.success:
        swarm.mark_task_complete(r.task_id, r.output)
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 16-LG1 results never propagate (real LangGraph) | **critical** | 1d |
| 16-CORR1 confidence asymmetry | med | 15m |
| 16-CORR2 stub leaks 100 chars | med | 30m |
| 16-LG2 task status not reflected | high | 30m |
| 16-OBS1 queen→coordinator comment | low | 1m |
