# Agent 25 — Topology Builder Auditor
**Model:** Claude Opus 4.7
**Scope:** the 5 decompose functions + `_QUEEN_NODE_NAMES` mapping.

## PURPOSE
Graph property checks (connectivity, diameter), adaptive routing trigger conditions, cost model.

## EVIDENCE BASE
`hive-swarm/swarm/nodes/queen.py:L21-L80`.

## WHAT WORKS ✅
- 5 decompose functions all signed-off as `(objective: str, max_agents: int) -> list[tuple[str, AgentRole]]` ✅.
- All decompose functions respect `max_agents` cap ✅.
- `_DECOMPOSE_FN` dict provides single dispatch point (`queen.py:L74-L80`).
- `factory.py:L40-L46` shares the same name set in `_QUEEN_NODE_NAMES`.

## TOPOLOGY × ROLES ANALYSIS

| Topology | Roles spawned | Pattern |
|---|---|---|
| hierarchical | researcher, architect, coder, tester, reviewer (5) | one role per work-stage |
| mesh | coder, tester, reviewer, researcher (4) | parallel collaboration |
| ring | researcher → coder → tester → reviewer (4) | sequential |
| star | security, optimizer, architect, coder (4) | independent specialised analyses |
| adaptive | aliased to hierarchical (5) | not actually adaptive |

## GRAPH PROPERTIES (theoretical)

| Topology | Connectivity | Diameter | Notes |
|---|---|---|---|
| hierarchical | tree (queen ↔ all) | 2 | always queen-mediated |
| mesh | conceptually all-to-all | 1 | implemented as parallel-then-merge |
| ring | linear chain | n-1 | implemented as parallel-then-merge (no actual chaining) |
| star | hub-spokes | 2 | implemented as parallel-then-merge |
| adaptive | hierarchical | 2 | no actual adaptivity |

**Critical observation**: at the LangGraph level, **all 5 topologies behave identically** — queen does Send fan-out → workers run in parallel → collect → consensus. The "topology" only changes the **role mix** in the worker set. There's no actual ring chaining, no actual mesh peer-to-peer, no actual star hub-spoke. Captured as **25-CORR1**.

## WHAT'S BROKEN 🔴

### 25-CORR1 (critical) — All "topologies" are parallel fan-outs at the graph level
`factory.py:L94-L96`: `for name in all_queen_names: builder.add_edge(name, "collect_results")`. Every queen node fans out via Send and joins at `collect_results`. The "topology" is just role selection.

This means:
- **Ring** is NOT sequential — researcher and reviewer run in parallel.
- **Mesh** has no peer-to-peer messaging.
- **Star** has no spoke isolation; the hub vs spoke distinction doesn't exist at runtime.

Either:
- Implement true ring (use `add_edge(researcher, coder)` chain instead of Send), OR
- Document that "topology" affects only role mix, not graph shape.

### 25-CORR2 (high) — Adaptive does not adapt
`queen.py:L80`: `"adaptive": _hierarchical_decompose`. Already flagged in `agent_15_queen.md` (15-CORR3).

### 25-CORR3 (med) — Mesh decompose returns 4 identical descriptions
`queen.py:L43-L48`:
```python
return [(f"Collaborate on: {objective}", role) for role in roles]
```
All 4 workers get the **same** `task_description`. With deterministic role-stub workers, all 4 produce nearly-identical outputs → consensus trivially agrees. With real LLMs, you'd want each worker to have a distinct prompt to get diverse perspectives.

### 25-OBS1 (low) — No "ring chain" parameter (e.g. researcher hands off to coder)
Even if topology stays parallel, exposing a `ring_pipeline` data structure would let consumers know which agent's output feeds the next.

### 25-OBS2 (low) — `_QUEEN_NODE_NAMES` duplicated between `factory.py` and `router.py`
Already flagged in 13-CORR1.

## WHAT'S MISSING 🟡
- No "topology adaptivity" trigger (e.g. mesh → switch to hierarchical when consensus repeatedly fails).
- No topology cost model (mesh = 4 LLM calls, hierarchical = 5, ring = 4, star = 4).
- No way for a user to register a custom topology.

## FIX RECOMMENDATION
```python
# queen.py — diff (mesh diversification)
def _mesh_decompose(objective: str, max_agents: int):
    count = min(max_agents, 4)
    perspectives = [
        ("coder", f"Implement: {objective}"),
        ("tester", f"Identify edge cases for: {objective}"),
        ("reviewer", f"Critique potential pitfalls in implementing: {objective}"),
        ("researcher", f"Find prior art and best practices for: {objective}"),
    ]
    return [(desc, role) for role, desc in perspectives[:count]]

# Real ring requires factory.py change:
# add_edge("ring_queen", "researcher_node") → "coder_node" → "tester_node" → "reviewer_node" → "consensus_node"
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 25-CORR1 topology label vs runtime mismatch | **critical** | 1wk (real ring + mesh) / 30m (doc) |
| 25-CORR2 adaptive doesn't adapt | high | 1d |
| 25-CORR3 mesh same prompt | high | 30m |
| 25-OBS1 ring chain absent | low | n/a (covered by CORR1) |
| 25-OBS2 duplicated map | med | 15m |
