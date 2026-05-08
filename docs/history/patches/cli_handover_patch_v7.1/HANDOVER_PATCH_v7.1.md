# Handover patch v7.1 — Tiny canonicalization (3 regression fixes)

> Pure correctness patch. No new features. Three small fixes you applied
> locally on v7, now baked into canon with a regression test for each.

## File map

| File | Fix ID | Change kind |
|---|---|---|
| `ai-provider-swarm-gateway/.../quota/tracker.py` | F-29-CORR1 | MODIFIED (~10 LoC delta) |
| `hive-swarm/swarm/graphs/factory.py` | F-13-CORR2 + F-13-CORR3 | MODIFIED (~5 LoC delta) |
| `hive-swarm/tests/test_v71_regressions.py` | regression for F-13-CORR2/3 + F-13A-CORR1 sanity | NEW |
| `ai-provider-swarm-gateway/tests/test_v71_regressions.py` | regression for F-29-CORR1 | NEW |

## Apply

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# DIFF FIRST — these files have your local fixes; skip the cp if your
# tree already matches:
diff ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py \
     cli_handover_patch_v7.1/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py
diff hive-swarm/swarm/graphs/factory.py \
     cli_handover_patch_v7.1/hive-swarm/swarm/graphs/factory.py

# If the diffs show your existing fixes are already there, the patch is
# a no-op for those files. Just copy the test files:
cp cli_handover_patch_v7.1/hive-swarm/tests/test_v71_regressions.py \
   hive-swarm/tests/
cp cli_handover_patch_v7.1/ai-provider-swarm-gateway/tests/test_v71_regressions.py \
   ai-provider-swarm-gateway/tests/

# If the diffs show v7.1's versions are different (e.g. cleaner code,
# better comments) AND your existing tests still pass, you can copy:
cp ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py.v7.bak
cp hive-swarm/swarm/graphs/factory.py \
   hive-swarm/swarm/graphs/factory.py.v7.bak

cp cli_handover_patch_v7.1/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/
cp cli_handover_patch_v7.1/hive-swarm/swarm/graphs/factory.py \
   hive-swarm/swarm/graphs/
```

> **Diff-first protocol** (per the v7 milestone retrospective): always
> diff before overwriting any file you've locally fixed. The handover
> pattern is now: ship the canonical version, but also ship the test
> that locks the behaviour, so the test passes on either your local fix
> OR the v7.1 canonical version.

## Verify

```bash
source .venv/bin/activate

# v7.1 regression tests (the headline)
pytest hive-swarm/tests/test_v71_regressions.py -q                            # ~6 tests
pytest ai-provider-swarm-gateway/tests/test_v71_regressions.py -q             # ~8 tests

# Full regression — must stay green
pytest swarm-shared/tests -q
pytest hive-swarm/tests -q
pytest ai-provider-swarm-gateway/tests -q

# Live regression: F-29-CORR1 reset works end-to-end
ai-provider-gateway quota increment --provider openai --requests 10 --tenant test_v71
ai-provider-gateway quota show --tenant test_v71 --json     # 10
ai-provider-gateway quota reset --provider openai --yes --tenant test_v71
ai-provider-gateway quota show --tenant test_v71 --json     # MUST be 0, not 10

# Live regression: F-13-CORR2 every topology builds
.venv/bin/python -c "
from swarm import SwarmConfig, build_swarm_graph
for top in ('hierarchical','mesh','ring','star','adaptive'):
    g = build_swarm_graph(SwarmConfig(topology=top))
    print(f'{top}: built ok')
"
```

## What v7.1 canonizes

### F-29-CORR1: `reset_usage()` is authoritative

**Was:** `reset_usage()` set `{used_requests: 0}` in-memory, then called
`_save_locked()` which merges with on-disk via `max(in_memory, on_disk)`.
So `max(0, 10) = 10` — the reset was completely swallowed.

**Now:** `reset_usage()` calls `_authoritative_save_locked()` (new private
method) which writes in-memory state verbatim, no merge. Caller's intent
is "make this the truth", not "advance counters to at least this value".

```python
def _authoritative_save_locked(self) -> None:
    """Write in-memory state verbatim, NO merge with on-disk."""
    # ... atomic_write_json under flock, but no max(ours, theirs) merge

def reset_usage(self, provider_id, window="daily"):
    # ... set in-memory to zero
    self._authoritative_save_locked()
    # Reload to ensure get_usage sees on-disk truth
    self._data = None
    self._ensure_loaded()
    return self.get_usage(provider_id, window)
```

Bonus: `_maybe_reset()` (the time-based auto-reset) also uses
`_authoritative_save_locked()` now — it had the same latent bug.

### F-13-CORR2: factory registers ALL 5 queen aliases

**Was:** `builder.add_node(queen_name, queen_node)` registered only the
queen alias for `config.topology`. But `route_task` returns names from
`QUEEN_NODE_NAMES` (all 5), so LangGraph's compiler rejected the routing
dict for any non-configured topology.

**Now:**
```python
all_queen_names = list(QUEEN_NODE_NAMES.values())
for queen_alias in all_queen_names:
    builder.add_node(queen_alias, queen_node)
```

All 5 aliases point at the same `queen_node` function. Topology selection
still happens **inside** `queen_node` via `_DECOMPOSE_FN[swarm.config.topology]`.
The factory just guarantees every routable destination exists.

### F-13-CORR3: mock graph mirrors SONA edges

**Was:** `_MockCompiledGraph.invoke`'s tier-1 and tier-2 branches called
`fast_agent_node` / `medium_agent_node` and stopped. The real graph has
`add_edge("fast_agent", "distill_node")` — so SONA pattern storage never
fired in mock-mode tests. They silently lied about working.

**Now:**
```python
if tier == "tier1_fast":
    state = fast_agent_node(state)
    state = distill_node(state)        # F-13-CORR3
elif tier == "tier2_medium":
    state = medium_agent_node(state)
    state = distill_node(state)        # F-13-CORR3
```

## Regression tests written

### Hive side (`test_v71_regressions.py`)

| Test | Asserts |
|---|---|
| `test_factory_registers_all_5_queen_aliases_for_hierarchical` | F-13-CORR2 — build doesn't crash + all 5 aliases present in compiled graph |
| `test_factory_registers_all_5_queen_aliases_for_each_topology` | F-13-CORR2 — true for every topology config |
| `test_mock_graph_distills_after_fast_agent` | F-13-CORR3 — tier-1 path increments `sona_cycle_count` |
| `test_mock_graph_distills_after_medium_agent` | F-13-CORR3 — tier-2 path increments `sona_cycle_count` |
| `test_mock_graph_distills_on_tier_3_too_unchanged` | F-13-CORR3 — didn't break tier-3 SONA |
| `test_worker_results_dedupe_still_idempotent` | F-13A-CORR1 — sanity that v7.1 didn't regress v6's reducer fix |

### Gateway side (`test_v71_regressions.py`)

| Test | Asserts |
|---|---|
| `test_reset_usage_zeros_after_increment` | F-29-CORR1 — headline bug fix |
| `test_reset_usage_writes_zero_to_disk` | F-29-CORR1 — on-disk JSON shows 0 |
| `test_reset_usage_does_not_affect_other_providers` | scope: provider |
| `test_reset_usage_does_not_affect_other_windows` | scope: window |
| `test_reset_usage_then_increment_starts_from_zero` | composability |
| `test_reset_usage_idempotent` | calling twice stays at 0 |
| `test_reset_usage_isolated_per_tenant` | scope: tenant (alice's reset doesn't touch bob) |
| `test_reset_usage_clears_reset_at` | also clears any scheduled reset timestamp |
| `test_cli_quota_reset_zeros_actual_disk_state` | end-to-end via CLI |

## What's preserved (regression matrix)

| Concern | Status |
|---|---|
| All v7 features (OpenAI embeddings, interactive HITL, multi-tenant) | ✅ |
| All 6 v7 canonical fixes (F-13A-CORR1, F-30-COSM1, F-18-CORR2, F-15-FWD1, F-17-ENV1, F-29-RET1) | ✅ |
| `SwarmConfig()` no-arg → stub mode | ✅ |
| Single-tenant default quota path | ✅ |
| Non-TTY auto-approve | ✅ |
| `increment()` remains merge-safe under concurrency | ✅ (only `reset_usage` changed semantics) |

## Rollback

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched
mv ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py.v7.bak \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py
mv hive-swarm/swarm/graphs/factory.py.v7.bak \
   hive-swarm/swarm/graphs/factory.py
rm hive-swarm/tests/test_v71_regressions.py
rm ai-provider-swarm-gateway/tests/test_v71_regressions.py
```

## Acceptance checklist

- [ ] `pytest hive-swarm/tests/test_v71_regressions.py -q` → green
- [ ] `pytest ai-provider-swarm-gateway/tests/test_v71_regressions.py -q` → green
- [ ] Full regression: all 3 suites still green
- [ ] Live: `quota reset` actually zeros after `quota increment N`
- [ ] Live: `build_swarm_graph(SwarmConfig(topology=X))` doesn't raise for any X
- [ ] Live: mock-mode tier-1 swarm increments `sona_cycle_count`

— end of patch —
