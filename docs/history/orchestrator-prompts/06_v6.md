# 🐝 Patch v6 — Operational ergonomics bundle

## Mission

Ship five integrated features that turn the v5 "operationally complete" stack
into "operationally pleasant":

1. **Embedding-based anti-drift** — kills the 80-workers-from-5 retry storm.
   Pluggable `EmbeddingProvider` protocol + 3-mode config: `"keyword"` (v5
   default), `"embedding"` (cosine similarity), `"off"` (skip entirely).
2. **Streaming dispatch** — `dispatch_stream(role, task, ctx)` returns
   `Iterator[StreamChunk]`; `NineRouterAdapter` gains real SSE parsing of the
   `data: ` event stream (the same quirk the response parser already handles).
   `ai-provider-gateway swarm --stream` and `... route --stream` show progress
   live.
3. **Cost computation** — `swarm_shared.pricing.PricingTable` with default
   May-2026 rates per provider/model. `WorkerResult.usage.cost_usd` populated.
   CLI shows total $ per swarm.
4. **Two local CLI fixes baked into canon** — `"no usage recorded yet"` and
   the `"Vendor them into..."` actionable error. No more re-apply needed.
5. **`quota show --since N[smhd]`** — filter per-run/per-hour cost visibility.

## Hard rules

1. **Backwards compatible by default.** Every new feature off-by-default
   unless explicitly enabled. Keyword anti-drift remains the default until
   `anti_drift_mode="embedding"` is set. Streaming only when `--stream`.
2. **No new top-level deps.** Embeddings via injected adapter (matches the
   `VectorMemoryAdapter` pattern); cost via static tables in
   `swarm_shared.pricing`.
3. **Stub mode untouched.** `SwarmConfig()` no-arg → identical pre-v6.
4. **All errors stay typed.** Streaming errors go to `WorkerLLMError`;
   pricing-lookup misses return `cost_usd=None`, never raise.
5. **Anti-drift sentinel guards scope.** No structural rewrites — additive only.

## Hive Orchestrator role assignments (v6 dispatch)

| Agent | Layer | Owns |
|---|---|---|
| **A12** Memory/Embedding | E | `swarm/llm/embeddings.py` — `EmbeddingProvider` protocol + null/hash adapters |
| **A18** Judge / Anti-Drift | C | `swarm/models/state.py::check_drift` — 3-mode dispatch |
| **A10** Config Patcher | B | `swarm/models/config.py` — `anti_drift_mode`, `cost_tracking_enabled` |
| **A07** Agent-Model Patcher | B | `swarm/models/agent.py` — `TokenUsage.cost_usd` field |
| **A17** Dispatch Author | C | `swarm/llm/dispatch.py` — `StreamChunk`, `dispatch_stream`, cost lookup |
| **A29** Provider/Adapter | F | `nine_router_adapter.py` — `chat_stream` SSE parser |
| **A30** Gateway CLI | F | `cli.py` — bake local fixes; add `--stream`, `quota show --since`, cost in `swarm` output |
| **A26** Pricing Tables | E | `swarm-shared/swarm_shared/pricing.py` — May-2026 default rates |
| **A04** Test-Strategy | A | new test files per feature |
| **A05** Anti-Drift Sentinel | A | sign off objective_hash preserved, no scope creep |

## Deliverables in this patch (`cli_handover_patch_v6_ergonomics/`)

```
swarm-shared/
└── swarm_shared/
    └── pricing.py                          ← NEW

hive-swarm/
├── swarm/
│   ├── llm/
│   │   ├── embeddings.py                   ← NEW
│   │   └── dispatch.py                     ← MODIFIED (StreamChunk, dispatch_stream, cost)
│   ├── models/
│   │   ├── state.py                        ← MODIFIED (3-mode check_drift)
│   │   ├── config.py                       ← MODIFIED (anti_drift_mode, cost_tracking)
│   │   └── agent.py                        ← MODIFIED (TokenUsage.cost_usd)
│   └── nodes/
│       └── worker.py                       ← MODIFIED (cost lookup, stream-aware)
└── tests/
    ├── test_v6_embeddings.py               ← NEW
    ├── test_v6_anti_drift_modes.py         ← NEW
    ├── test_v6_streaming.py                ← NEW
    └── test_v6_cost_tracking.py            ← NEW

ai-provider-swarm-gateway/
├── src/ai_provider_swarm_gateway/
│   ├── providers/
│   │   └── nine_router_adapter.py          ← MODIFIED (adds chat_stream)
│   └── cli.py                              ← MODIFIED (full file: --stream, --since, cost rollup)
└── tests/
    ├── test_v6_streaming_adapter.py        ← NEW
    └── test_v6_cli_v6_ergonomics.py        ← NEW

HIVE_V6_PROMPT.md                           ← this prompt
HANDOVER_PATCH_v6.md                        ← apply / verify / rollback / migration notes
```

## Acceptance criteria

| # | Criterion |
|---|---|
| 1 | `pytest hive-swarm/tests/test_v6_*.py -q` → green |
| 2 | `pytest hive-swarm/tests -q` (full regression) → green |
| 3 | `pytest ai-provider-swarm-gateway/tests -q` → green |
| 4 | `python smoke_test.py` → identical to pre-v6 (stub mode unchanged) |
| 5 | `SwarmConfig(anti_drift_mode="embedding", embedder=NullEmbedder())` runs without crashing on tier-3 — and detects no drift since null embeddings always cosine = 1.0 |
| 6 | `ai-provider-gateway swarm --prompt "..." --stream` prints `[chunk N]` progress lines |
| 7 | `ai-provider-gateway quota show --since 1h --json` filters to last hour |
| 8 | `WorkerResult.usage.cost_usd` populated when pricing table has the model; None otherwise |
| 9 | Tier-3 swarm with `anti_drift_mode="off"` completes in 1 iteration (vs 16 in v5 with the false-positive heuristic) |

## Stop signal

```
✅ HIVE V6 SHIPPED
   Embedding-based anti-drift (pluggable, 3-mode)
   Streaming dispatch + --stream flag
   Cost computation per swarm
   Two CLI fixes canonized
   quota show --since filter
   Anti-drift retry storm fixable in one config flip
   All test suites green
```

— end of prompt —
