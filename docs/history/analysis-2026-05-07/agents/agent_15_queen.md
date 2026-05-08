# Agent 15 — Queen Node Auditor
**Model:** Claude Opus 4.6
**Scope:** `hive-swarm/swarm/nodes/queen.py`

## PURPOSE
`Send()` fan-out correctness, hierarchical / mesh / ring / star / adaptive decompose functions, max-agents bound (≤100).

## PUBLIC SURFACE (verified)
- 5 decompose functions: `_hierarchical_decompose`, `_mesh_decompose`, `_ring_decompose`, `_star_decompose`, plus adaptive (aliased to hierarchical).
- `queen_node(state) -> list[Send | dict]`
- `fast_agent_node`, `medium_agent_node` (Tier-1, Tier-2 stubs).

## WHAT WORKS ✅
- LangGraph `Send` import wrapped in `try / except ImportError` ✅ (`queen.py:L13-L17`) — framework still importable.
- All 5 topologies have a decompose function in `_DECOMPOSE_FN` (`queen.py:L74-L80`) ✅.
- `queen_node` correctly bumps `iteration` and fails when `max_iterations` exceeded BEFORE doing work (`queen.py:L93-L96`) ✅.
- `objective_hash` is included in every `QueenDirective` (`queen.py:L120`) ✅ — anti-drift propagated to workers.
- `AgentState.task_context` carries the directive payload (`queen.py:L127`) ✅.
- `Send("worker_node", agent_state.to_json_dict())` is the correct LangGraph pattern (`queen.py:L130`) ✅.

## WHAT'S BROKEN 🔴

### 15-LG1 (critical) — `queen_node` returns `[swarm.to_json_dict()]` when `Send is None` — but graph expects `list[Send]`
`queen.py:L142-L144`:
```python
return send_list if send_list else [swarm.to_json_dict()]
```
If `send_list` is empty (because `Send is None` due to LangGraph absence), returns a one-element list of state dict. LangGraph's `add_conditional_edges` expects a `Send | str | list[Send]` shape. Returning a list-of-dict will not route correctly. Mock graph papers over it (`factory.py:L143-L148`). **Real LangGraph deployment without `langgraph.types.Send` (e.g. very old version) will silently break.** Either bump the dep pin or raise loudly.

### 15-CORR1 (high) — `_hierarchical_decompose` uses fixed 5 roles regardless of objective
`queen.py:L21-L37`. For an objective like "fix a typo", the hierarchical decompose still spawns researcher + architect + coder + tester + reviewer. That's 5 LLM calls for a typo fix. The router is supposed to catch this via Tier 1, but:
- If complexity heuristic mis-scores (very plausible — see Agent 14), the typo lands in Tier 3.
- The decomposition has **no objective-aware pruning**.

Recommend: pass `complexity_score` into `decompose()` and skip non-essential roles below a threshold.

### 15-CORR2 (med) — `_star_decompose` ignores `max_agents` for spokes < 4 only
`queen.py:L65-L71`:
```python
spokes = [(security, ...), (optimizer, ...), (architect, ...), (coder, ...)]
return spokes[: min(len(spokes), max_agents)]
```
Always returns at most 4 spokes regardless of `max_agents=20`. That's actually correct for star (one hub + N spokes), but if a user configures `max_agents=2`, only `security` and `optimizer` run — **architect and coder are dropped silently**. Likely not the intent. Document or rotate which roles get dropped.

### 15-CORR3 (high) — `adaptive` topology silently aliases to `hierarchical`
`queen.py:L80`: `"adaptive": _hierarchical_decompose`. The synthesis report claims "adaptive starts hierarchical, routes" — but there is no actual adaptive routing. Once `queen_node` is invoked it always uses the hierarchical decomposition; nothing escalates topology mid-run. Either:
- Implement true adaptivity (track previous-iteration agreement and switch topology), OR
- Rename `adaptive` to `auto` and document that auto = hierarchical-default.

### 15-LG2 (med) — `Send` payloads include the full directive dict, which is large
`queen.py:L127-L132`. Each `Send` carries `task_context = directive.model_dump(mode="json")` — that's `task` (with all fields) + `shared_context` (objective + iteration). For 5 workers × 4KB directive each = 20KB of duplicated state per fan-out. With checkpointing, this 20KB is written every iteration. Optimisation: pass only `task_id` + `agent_id`, let workers read the rest from a shared store.

### 15-CORR4 (low) — `secrets` import unused
`queen.py:L9`. Import `secrets` is never referenced. Dead import.

### 15-LG3 (med) — `swarm.agents = list(swarm.agents) + new_agents` — the rebuilt list triggers `_agent_count_le_config` and `_agents_bounded` validators
`queen.py:L137`. Each iteration, all existing + new agents revalidate. If `max_agents=100` and 99 agents exist, adding 5 more raises ValidationError. Currently `queen_node` doesn't catch this — the swarm fails. Add an explicit length check before assignment with a graceful failure message.

### 15-OBS1 (low) — Stub outputs are not deterministic across runs
`fast_agent_node` and `medium_agent_node` return `f"[FAST] Heuristic result for: {swarm.objective}"` — deterministic ✅. But `worker_node` (separate file) generates outputs depending on role; in production with LLM, these will be non-deterministic and break tests that assert exact output strings.

## WHAT'S MISSING 🟡
- No `_adaptive_decompose` actually exists (re-uses hierarchical).
- No "smart fan-out reducer" — each worker independently decides task scope.
- No retry-with-different-topology fallback.
- No timeout per `Send()` — a hung worker hangs the swarm.

## FIX RECOMMENDATION
```python
# queen.py — diff
def _adaptive_decompose(
    objective: str,
    max_agents: int,
    *,
    prev_consensus_agreement: float = 1.0,
) -> list[tuple[str, AgentRole]]:
    """If prev consensus was weak (<0.5), escalate to mesh; else hierarchical."""
    if prev_consensus_agreement < 0.5:
        return _mesh_decompose(objective, max_agents)
    return _hierarchical_decompose(objective, max_agents)

_DECOMPOSE_FN = {
    ...,
    "adaptive": _adaptive_decompose,
}

# in queen_node:
if Send is None and not send_list:
    raise RuntimeError(
        "langgraph.types.Send unavailable; install langgraph>=0.3.0 "
        "or use _MockCompiledGraph for tests."
    )

# remove unused import
# import secrets   ← DELETE
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 15-LG1 silent Send fallback | **critical** | 15m |
| 15-CORR1 objective-blind decompose | high | 1d |
| 15-CORR2 star drops roles | med | 30m |
| 15-CORR3 adaptive==hierarchical | high | 1d |
| 15-LG2 large Send payloads | med | 1d |
| 15-CORR4 dead import | low | 1m |
| 15-LG3 agent-cap blast | med | 30m |
