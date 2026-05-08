# 🐝 Patch v7.1 — Tiny canonicalization (3 regression fixes)

## Mission

Bake your three local re-apply fixes from v7 into canon. No features.
Each fix gets one regression test named for its canonical ID so future
patches can't silently re-introduce the bug.

## Fixes

| ID | Fix | File | LoC |
|---|---|---|---|
| **F-29-CORR1** | `QuotaTracker.reset_usage` must not merge with on-disk state | `quota/tracker.py` | ~10 |
| **F-13-CORR2** | `factory.py` must register all 5 queen aliases | `swarm/graphs/factory.py` | ~3 |
| **F-13-CORR3** | `_MockCompiledGraph.invoke` must call `distill_node` after fast_agent / medium_agent | `swarm/graphs/factory.py` | ~2 |

## Hard rules

1. **Pure correctness.** No new features, no signature changes.
2. **Idempotent re-apply.** If your local tree already has any of these
   fixes (which it does), re-applying must be a no-op (the diff matches).
3. **Each fix gets a regression test.** Named for its ID. Failing
   immediately when the bug returns.

## Acceptance

| # | Criterion |
|---|---|
| 1 | `pytest hive-swarm/tests/test_v71_regressions.py -q` → green |
| 2 | `pytest ai-provider-swarm-gateway/tests/test_v71_regressions.py -q` → green |
| 3 | Full regression: all suites still green |
| 4 | `tracker.reset_usage(provider)` zeros the on-disk file even when prior counter > 0 |
| 5 | `build_swarm_graph(SwarmConfig(topology="ring"))` registers all 5 queen aliases (no missing-destination errors) |
| 6 | Mock graph tier-1 / tier-2 path increments `final.sona_cycle_count` |

## Stop signal

```
✅ V7.1 SHIPPED
   F-29-CORR1: reset_usage authoritative
   F-13-CORR2: all 5 queen aliases registered
   F-13-CORR3: mock SONA edges mirror real graph
   3 regression tests; all suites green
```

— end of prompt —
