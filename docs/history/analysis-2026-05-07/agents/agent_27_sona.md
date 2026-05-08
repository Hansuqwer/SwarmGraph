# Agent 27 — SONA Loop Auditor
**Model:** Claude Opus 4.7
**Scope:** `hive-swarm/swarm/nodes/sona.py` (`distill_node`, `memory_retrieve_node`)

## PURPOSE
RETRIEVE → JUDGE → DISTILL → CONSOLIDATE → ROUTE pipeline integrity, `sona_min_confidence=0.7` justification, infinite-loop guard.

## PUBLIC SURFACE (verified)
- `distill_node(state) -> dict` — DISTILL + CONSOLIDATE
- `memory_retrieve_node(state) -> dict` — RETRIEVE

## WHAT WORKS ✅
- `distill_node` guards on `swarm.status in ("distilling", "completed")` (`sona.py:L25-L28`) ✅.
- `swarm.config.sona_enabled` gates both DISTILL and CONSOLIDATE (`sona.py:L31, L41`) ✅.
- DISTILL uses `swarm.memory.distill()` and logs removed count (`sona.py:L31-L37`) ✅.
- CONSOLIDATE stores `final_output` keyed by `pattern:{objective_hash}:{iteration}` (`sona.py:L41-L57`) ✅ — clean key scheme, deterministic.
- Score derived from consensus agreement (`sona.py:L48`) ✅ — high-agreement patterns get high score.
- ROUTE: `swarm.increment_sona()` + `status = "completed"` (`sona.py:L60-L62`) ✅.
- `memory_retrieve_node` fully gated by `sona_enabled` (`sona.py:L72-L75`) ✅.
- Promotes score of every retrieved entry (EWC++ analog) (`sona.py:L94-L95`) ✅.

## WHAT'S BROKEN 🔴

### 27-LG1 (high) — `memory_retrieve_node` retrieves patterns but DOES NOT inject them anywhere readable
`sona.py:L82-L92`:
```python
relevant = swarm.memory.search(...)
if relevant:
    context_injection = "\n".join(f"[PATTERN ...] ..." for e in relevant)
    swarm.append_history("memory_retrieve", {...})
    for e in relevant:
        swarm.memory.promote_score(...)
```
The `context_injection` string is **built and discarded** — never written to state, never seen by `queen_node` or `worker_node`. The retrieval is a no-op for downstream nodes. Either:
- Add a `swarm.retrieved_context: list[str]` field that queen_node reads.
- Inject into `QueenDirective.shared_context["retrieved_patterns"]`.

This is a **substantial functionality gap**: SONA retrieves but cannot influence next decisions.

### 27-CORR1 (high) — `distill_node` runs DISTILL **before** CONSOLIDATE — risk of evicting the new pattern
`sona.py:L31-L57`:
1. `swarm.memory.distill()` removes entries below `sona_min_score=0.7`.
2. Then stores `final_output` with `score = agreement_fraction`.

If `agreement_fraction < 0.7`, the freshly-stored pattern would be evicted by the **next** distill call (next swarm run). Acceptable behaviour — low-confidence patterns shouldn't persist. But the **order** is right (distill → consolidate, so the new entry isn't immediately evicted).

**However**: if `agreement_fraction = 0.71` and `sona_min_score = 0.7`, the entry survives but barely. With `_cap()` evicting lowest-score on full memory, this entry is first to go. This is documented behaviour but worth surfacing.

### 27-CORR2 (med) — `pattern:{objective_hash}:{iteration}` overwrites on retry
If the swarm re-runs same objective, `objective_hash` is the same. Iteration 1 vs iteration 2 will both produce keys `pattern:HASH:1` and `pattern:HASH:2` — distinct. ✅. **But** if the user reuses the same objective in a NEW swarm session, both runs produce `pattern:HASH:1`. The second run's `store()` correctly de-dupes ✅. However, that means we lose the first run's pattern even if it had a better score. Recommend keep-best-score policy in `store()` for same-key re-stores, OR include `swarm_id` in the key.

### 27-CORR3 (low) — `swarm.config.sona_min_confidence` is conflated with `swarm.memory.sona_min_score`
`config.py:L41`: `sona_min_confidence = 0.7`. `memory.py:L52`: `sona_min_score = 0.7`. Two different fields, same value, never wired together. The retrieval `min_score` parameter (`sona.py:L80`) uses `swarm.config.sona_min_confidence` ✅, but `distill()` uses `swarm.memory.sona_min_score` (instance default). They could drift. Either alias them or pass the config value through to memory at construction.

### 27-OBS1 (low) — No upper bound on `sona_cycle_count`
`state.py:L92`: `Field(default=0, ge=0)`. With `max_iterations=50` and SONA running once per accepted output, this stays bounded. ✅. But if a future fix wraps the SONA loop into multiple intra-graph cycles, this would grow unbounded. Add `le=10_000`.

## WHAT'S MISSING 🟡
- No SONA telemetry (distillations / consolidations / retrievals counters).
- No "negative pattern" storage (failed runs to avoid).
- No A/B comparison: does retrieval actually improve outcomes? Need a measurement harness.
- The retrieval results not propagated (27-LG1) means SONA gives **zero** runtime benefit currently.

## FIX RECOMMENDATION
```python
# sona.py — diff (close the loop)
def memory_retrieve_node(state):
    swarm = SwarmState.model_validate(state)
    if not swarm.config.sona_enabled:
        return swarm.to_json_dict()

    relevant = swarm.memory.search(
        swarm.objective,
        namespace=swarm.config.memory_namespace,
        top_k=3,
        min_score=swarm.config.sona_min_confidence,
    )

    if relevant:
        # NEW: write retrieved patterns into state for queen/workers to read
        swarm.retrieved_context = [
            {"key": e.key, "value": e.value, "score": e.score, "tags": e.tags}
            for e in relevant
        ]
        swarm.append_history("memory_retrieve", {
            "retrieved_count": len(relevant),
            "top_score": relevant[0].score,
        })
        for e in relevant:
            swarm.memory.promote_score(e.key, e.namespace)

    return swarm.to_json_dict()

# Plus: add `retrieved_context: list[dict] = Field(default_factory=list, max_length=10)`
# to SwarmState in state.py.
# Plus: have queen_node read swarm.retrieved_context and include in QueenDirective.shared_context.
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 27-LG1 retrieval is no-op | high | 1d (full close-the-loop) |
| 27-CORR1 distill-before-consolidate doc | low | 5m |
| 27-CORR2 cross-session key reuse | med | 15m |
| 27-CORR3 two min_score fields | low | 15m |
| 27-OBS1 sona_cycle_count cap | low | 1m |
| Missing telemetry | med | 1d |

**Verdict on `sona_min_confidence=0.7`:** the threshold is reasonable as a default ✅, but:
- It's never empirically justified.
- It's identical to `sona_min_score` (both default 0.7) without coordination.
- A 0.7 threshold means agreement_fraction in [0.7, 1.0] gets stored — a wide band.
