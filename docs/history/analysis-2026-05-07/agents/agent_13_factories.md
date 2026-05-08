# Agent 13 — Graph Factory Auditor
**Model:** Claude Opus 4.7
**Scope:** `hive-swarm/swarm/graphs/factory.py`, `ai-provider-swarm-gateway/.../graph/builder.py`

## PURPOSE
Verify node registration, edge correctness, conditional-edge exhaustiveness, terminal nodes, recursion limits.

## EVIDENCE BASE
- `hive-swarm/swarm/graphs/factory.py:L1-L165` (verified end-to-end).
- `ai-provider-swarm-gateway/.../graph/builder.py` (not fetched in this run; partial findings only).

## WHAT WORKS ✅ — `hive-swarm/swarm/graphs/factory.py`

- Optional LangGraph import via `try / except ImportError` (`factory.py:L23-L31`) — framework imports without LangGraph ✅.
- Mock fallback `_MockCompiledGraph` (`factory.py:L131-L165`) provides a real-shape pseudo-runtime for tests.
- Every node from the agent roster is registered (`factory.py:L62-L72`):
  - `memory_retrieve`, `route_task`, `fast_agent`, `medium_agent`, `<topology>_queen`, `worker_node`, `collect_results`, `consensus_node`, `approval_node`, `judge_node`, `distill_node` ✅.
- Conditional edges:
  - `route_task → {fast_agent, medium_agent, *queens}` (`factory.py:L82-L88`) ✅.
  - `consensus_node → {approval_node, judge_node, end}` (`factory.py:L102-L107`) ✅.
  - `approval_node → {judge_node, end}` (`factory.py:L110-L115`) ✅.
  - `judge_node → {distill_node, route_task, end}` (`factory.py:L118-L123`) ✅.
- Default checkpointer wraps `InMemorySaver` with `SwarmRedactingCheckpointer` ✅ (`factory.py:L126-L130`).
- Single-source `_QUEEN_NODE_NAMES` dict prevents queen-name drift (`factory.py:L40-L46`) ✅.

## WHAT'S BROKEN 🔴

### 13-LG1 (high) — `worker_node` is registered but NOT wired into the graph
`factory.py:L68`: `builder.add_node("worker_node", worker_node)`.
But there is no `add_edge` to `worker_node` from anywhere. The `Send()` calls in `queen_node` target `"worker_node"` — that's how LangGraph routes Send payloads — so the wiring is implicit.

However: the `add_edge("<queen_name>", "collect_results")` (`factory.py:L94-L95`) creates a direct queen→collect edge **without** going through `worker_node`. In LangGraph 0.3, when a node returns `list[Send]`, the graph dispatches those Sends in parallel and **does** trigger the named target node. But the `add_edge(queen, collect_results)` is the **fan-in** edge that runs after all Sends complete. This is the correct pattern ✅, but the absence of `add_edge(queen, worker_node)` is **easy to mis-read**. Add a comment.

### 13-CORR1 (med) — `_QUEEN_NODE_NAMES` defined twice
`factory.py:L40-L46` AND `nodes/router.py:L62-L68` define the same dict. Drift risk. Move to `models/types.py` or a shared `swarm._constants` module.

### 13-LG2 (med) — Mock `_MockCompiledGraph.invoke` does not handle the `awaiting_approval` resume path
`factory.py:L155`:
```python
if swarm_status == "awaiting_approval":
    state = approval_node(state)
```
The mock calls `approval_node` directly which calls the local fallback `interrupt(payload) → {"decision": "approve"}` — auto-approves everything. **For tests this is OK** but a developer who relies on the mock to test denial paths gets silently wrong behaviour. Add a `mock_approval_decision: str = "approve"` parameter or a fixture-style override.

### 13-LG3 (high) — No `recursion_limit` set on `builder.compile`
`factory.py:L130`: `return builder.compile(checkpointer=cp)`. Default LangGraph recursion limit is **25**. With `judge_node → route_task` retry loop and `max_iterations: le=50` allowed in `SwarmConfig`, the graph can theoretically attempt more iterations than the recursion limit allows, raising `GraphRecursionError` mid-swarm. Set `recursion_limit = max_iterations * 8` (heuristic: 8 nodes per iteration) or expose as a config field.

### 13-CORR2 (med) — `route_task` returns string keys but `routing_targets` dict uses identity mapping
`factory.py:L84-L88`:
```python
routing_targets = {
    "fast_agent": "fast_agent",
    "medium_agent": "medium_agent",
    **{name: name for name in all_queen_names},
}
builder.add_conditional_edges("route_task", route_task, routing_targets)
```
Identity mapping is technically valid in LangGraph but redundant — you can pass `route_task` directly without the dict OR use the dict to remap. Currently both add cognitive overhead. Either drop the dict or use it for remapping.

### 13-LG4 (high) — `distill_node → END` always — but the SONA loop docstring says "RETRIEVE → JUDGE → DISTILL → CONSOLIDATE → ROUTE (loop)"
`factory.py:L126`: `builder.add_edge("distill_node", END)`. The SONA loop is **not actually a loop** — it terminates. `judge_node` can route back to `route_task` (retry) but `distill_node` cannot. So the "ROUTE" step in SONA is the **next swarm invocation**, not a within-graph cycle. Either:
- Document this in the SONA loop docstring (`nodes/sona.py:L10-L11`), OR
- Implement a real intra-graph SONA cycle.

### 13-T1 (low) — `builder = StateGraph(dict)` — no Pydantic-aware reducers
The graph state is `dict`. Every node does `SwarmState.model_validate(state)` on entry and `swarm.to_json_dict()` on exit. This is the safest pattern (per `research/langgraph_best_practices.md`) ✅, **but** it means parallel `Send()` workers' returns are merged via the default `dict` reducer (last-write-wins on overlapping keys). The fact that `worker_node` returns `{"_worker_result": ..., "_agent_id": ...}` and `collect_results_node` reads `swarm.worker_results` means workers must populate `worker_results` themselves OR the merge step must be explicit. Verified: `_MockCompiledGraph` manually appends to `worker_results` (`factory.py:L150-L154`), but the **real** LangGraph path relies on a reducer. **There is no reducer registered.** Inspection of `worker_node`'s return shows `{"_worker_result": ...}` — these underscore keys are **not** read by `collect_results_node` (which reads `swarm.worker_results`). This is a **latent bug** in the real LangGraph path. The mock path papers over it.

## WHAT'S MISSING 🟡
- No `interrupt_before=["approval_node"]` declared on compile — relies on `interrupt()` inside the node, which works but is less debugger-friendly.
- No `interrupt_after=[...]` for inspection points.
- Builder for the ai-provider-swarm-gateway not analysed (file not fetched).
- No graph visualisation hook (`graph.get_graph().draw_mermaid_png()`).

## FIX RECOMMENDATION
```python
# factory.py — diff
from operator import add
from typing import Annotated, TypedDict

class _SwarmGraphState(TypedDict, total=False):
    # explicit reducer for parallel Send fan-out
    worker_results: Annotated[list[dict], add]
    # ... (other fields)

builder = StateGraph(_SwarmGraphState)
# ...
return builder.compile(
    checkpointer=cp,
    interrupt_before=["approval_node"],
    recursion_limit=max(25, config.max_iterations * 8),
)
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 13-LG1 worker_node wiring comment | low | 5m |
| 13-CORR1 duplicated `_QUEEN_NODE_NAMES` | med | 15m |
| 13-LG2 mock approval | med | 30m |
| 13-LG3 recursion_limit | high | 5m |
| 13-CORR2 identity dict | low | 5m |
| 13-LG4 SONA-loop doc drift | med | 30m |
| 13-T1 missing reducer (latent bug) | **critical** | 1d |
