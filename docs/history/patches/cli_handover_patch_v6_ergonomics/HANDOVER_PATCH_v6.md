# Handover patch v6 — Operational ergonomics bundle

> Five integrated features, all backwards-compatible, all additive.
> Stub mode unchanged. Defaults preserve v5 behaviour. Opt-in everywhere.

## Apply

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# --- swarm-shared (NEW pricing module) ---
cp cli_handover_patch_v6_ergonomics/swarm-shared/swarm_shared/pricing.py \
   swarm-shared/swarm_shared/pricing.py
cp cli_handover_patch_v6_ergonomics/swarm-shared/tests/test_pricing.py \
   swarm-shared/tests/test_pricing.py

# --- hive-swarm (modified files: backup first) ---
cp hive-swarm/swarm/llm/__init__.py            hive-swarm/swarm/llm/__init__.py.v5.bak
cp hive-swarm/swarm/llm/dispatch.py            hive-swarm/swarm/llm/dispatch.py.v5.bak
cp hive-swarm/swarm/nodes/worker.py            hive-swarm/swarm/nodes/worker.py.v5.bak
cp hive-swarm/swarm/models/agent.py            hive-swarm/swarm/models/agent.py.v5.bak
cp hive-swarm/swarm/models/config.py           hive-swarm/swarm/models/config.py.v5.bak
cp hive-swarm/swarm/models/state.py            hive-swarm/swarm/models/state.py.v5.bak

cp cli_handover_patch_v6_ergonomics/hive-swarm/swarm/llm/embeddings.py     hive-swarm/swarm/llm/
cp cli_handover_patch_v6_ergonomics/hive-swarm/swarm/llm/__init__.py       hive-swarm/swarm/llm/
cp cli_handover_patch_v6_ergonomics/hive-swarm/swarm/llm/dispatch.py       hive-swarm/swarm/llm/
cp cli_handover_patch_v6_ergonomics/hive-swarm/swarm/nodes/worker.py       hive-swarm/swarm/nodes/
cp cli_handover_patch_v6_ergonomics/hive-swarm/swarm/models/agent.py       hive-swarm/swarm/models/
cp cli_handover_patch_v6_ergonomics/hive-swarm/swarm/models/config.py      hive-swarm/swarm/models/
cp cli_handover_patch_v6_ergonomics/hive-swarm/swarm/models/state.py       hive-swarm/swarm/models/

# New tests
cp cli_handover_patch_v6_ergonomics/hive-swarm/tests/test_v6_*.py hive-swarm/tests/

# --- ai-provider-swarm-gateway ---
cp ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py.v5.bak
cp ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py.v5.bak

cp cli_handover_patch_v6_ergonomics/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/
cp cli_handover_patch_v6_ergonomics/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/

# New tests
cp cli_handover_patch_v6_ergonomics/ai-provider-swarm-gateway/tests/test_v6_*.py \
   ai-provider-swarm-gateway/tests/

# No re-install needed (editable installs pick up the changes)
```

> **Important note about `nine_router_adapter.py`:** v6 ADDS a `chat_stream`
> method but **leaves the rest of your local-edited file alone in spirit**.
> If you've made significant local changes to the existing methods (like
> `call()` returning `GatewayResponse`), the v6 file in this patch may have
> reverted those. Diff before applying:
> ```bash
> diff ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py \
>      cli_handover_patch_v6_ergonomics/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py
> ```
> If the diff shows your `call()` is missing, **don't apply the v6 file
> wholesale** — instead, just append the `chat_stream`, `_parse_sse_data_line`,
> `_stream_event_to_chunk`, and `post_json_stream` additions to your existing
> file.

## Verify

```bash
source .venv/bin/activate

# v6-specific tests
pytest swarm-shared/tests/test_pricing.py -q                                # ~15 tests
pytest hive-swarm/tests/test_v6_embeddings.py -q                            # ~20 tests
pytest hive-swarm/tests/test_v6_anti_drift_modes.py -q                      # ~16 tests
pytest hive-swarm/tests/test_v6_streaming.py -q                             # ~15 tests
pytest hive-swarm/tests/test_v6_cost_tracking.py -q                         # ~10 tests
pytest ai-provider-swarm-gateway/tests/test_v6_streaming_adapter.py -q      # ~12 tests
pytest ai-provider-swarm-gateway/tests/test_v6_cli_ergonomics.py -q         # ~12 tests

# Full regression
pytest swarm-shared/tests -q
pytest hive-swarm/tests -q
pytest ai-provider-swarm-gateway/tests -q

# Stub-mode smoke (must match pre-v6)
.venv/bin/python smoke_test.py

# The 80-workers-from-5 fix: anti-drift off ⇒ no retry storm
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
ai-provider-gateway swarm \
  --prompt "implement comprehensive distributed authentication architecture" \
  --backend gateway --provider 9router \
  --anti-drift off \
  --max-agents 5 --json --show-workers
# expected: iterations: 1, worker_count: 5, total_cost_usd: 0 (free model)

# Streaming smoke
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
ai-provider-gateway swarm \
  --prompt "implement add(a,b)" \
  --backend gateway --provider 9router \
  --stream --anti-drift off --max-agents 3
# expected: workers run with llm_streamed=True in metadata

# Quota show with --since
ai-provider-gateway quota show --since 1h
ai-provider-gateway quota show --since 7d --json
```

## What v6 adds

### 1. Embedding-based anti-drift (3-mode)

```python
config = SwarmConfig(
    anti_drift_mode="off",         # NEW: skip drift detection (fixes retry storm)
    # OR
    anti_drift_mode="keyword",     # default — v5 behaviour preserved
    # OR
    anti_drift_mode="embedding",   # cosine via injected EmbeddingProvider
    anti_drift_similarity_threshold=0.3,
)
```

For embedding mode, plug in the embedder:
```python
from swarm.llm.embeddings import HashEmbedder, set_default_embedder

set_default_embedder(HashEmbedder())   # deterministic, no network, 32-dim
# OR
from swarm.llm.embeddings import GatewayEmbedder
set_default_embedder(GatewayEmbedder(provider_id="openai"))
```

`HashEmbedder` is a fast deterministic bag-of-words hash (32 dims, no model
download). Suitable for tests and smoke runs where you don't have a real
embeddings API. For production, `GatewayEmbedder` calls any registered
gateway adapter that implements `embed()`.

**The 80-workers-from-5 fix:** set `anti_drift_mode="off"` on code-gen
workloads. The retry storm disappears.

### 2. Streaming dispatch

```python
config = SwarmConfig(llm_backend="gateway", llm_stream_enabled=True)
```

Or via env: `HIVE_SWARM_LLM_STREAM=1`. Or via CLI: `--stream`.

Workers consume `dispatcher.dispatch_stream(...) -> Iterator[StreamChunk]`
and concatenate chunks into the final `WorkerResult.output`. Same return
shape as non-streaming; chunks are an internal detail.

`NineRouterAdapter.chat_stream` parses real SSE (`data: {...}` events,
ignoring `[DONE]` sentinel). Adapters without `chat_stream` fall back to
single-chunk emission so the dispatcher contract holds.

### 3. Cost computation

```python
final = SwarmState.from_json_dict(result)
for r in final.worker_results:
    if r.usage and r.usage.cost_usd is not None:
        print(f"{r.agent_role}: ${r.usage.cost_usd:.4f}")
```

Pricing table at `swarm_shared.pricing.DEFAULT_PRICING_TABLE`. May-2026
rates for Anthropic Opus/Sonnet/Haiku, OpenAI GPT-4o*, free providers
(9router/mock/ollama/stepfun) priced at $0.

Lookup misses (unknown model id) leave `cost_usd=None` — never raise. CLI
renders missing as `—`.

Override the table:
```python
from swarm_shared.pricing import PricingTable
custom = PricingTable.from_json_file(Path("my_prices.json"))
# pass into estimate_cost(... table=custom)
```

### 4. Two CLI fixes baked into canon

| Fix | Where | What changed |
|---|---|---|
| Empty quota message | `quota show` (no entries) | now emits `[no usage recorded yet]` (was inconsistent across versions) |
| Missing-gateway error | `route` (when upstream import fails) | now includes the `Vendor them into src/...` actionable path list, pointing at PATCH_NOTE |

These are in the v6 `cli.py` template — future patches won't overwrite them
because they're now the canonical strings.

### 5. `quota show --since`

```bash
ai-provider-gateway quota show --since 30s
ai-provider-gateway quota show --since 5m
ai-provider-gateway quota show --since 1h
ai-provider-gateway quota show --since 7d
```

Filters to entries with `reset_at` within the window of NOW. Entries
without `reset_at` (unbounded windows like "monthly with no scheduled
reset") are included conservatively. Use `--json` for parseable output.

## What's preserved (regression matrix)

| Concern | Status |
|---|---|
| `SwarmConfig()` no-arg → stub mode, no LLM, no embeddings, no cost | ✅ |
| `WorkerResult.usage = None` for fully-empty responses | ✅ |
| `WorkerResult.usage.cost_usd = None` for unknown models | ✅ |
| Reducer-friendly worker return shape | ✅ |
| F-07-CORR3 vote truncation | ✅ |
| F-15-LG4 queen Send fan-out | ✅ |
| F-13A operator.add reducer | ✅ |
| F-27A SONA-loop closure | ✅ |
| Anti-drift `objective_hash` end-to-end | ✅ |
| All v5 features (per-role models, tier-2 gateway, swarm CLI) | ✅ |

## What's intentionally deferred to v7

- **Interactive HITL UX in the gateway CLI.** v6 still defaults to auto-approve
  for non-interactive runs. Proper `Command(resume=ApprovalDecision)` flow
  would need a TTY-detecting prompt with single-use token echo.
- **Real embeddings adapter.** v6 ships `HashEmbedder` (deterministic hash)
  and `GatewayEmbedder` (lazy-binds to any adapter with `embed()`); a
  shipped `OpenAIEmbeddingAdapter` would be its own thing.
- **Per-tenant quota isolation.** Single-tenant JSON file per process pool
  is still the model.

## Rollback

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched
mv hive-swarm/swarm/llm/__init__.py.v5.bak     hive-swarm/swarm/llm/__init__.py
mv hive-swarm/swarm/llm/dispatch.py.v5.bak     hive-swarm/swarm/llm/dispatch.py
mv hive-swarm/swarm/nodes/worker.py.v5.bak     hive-swarm/swarm/nodes/worker.py
mv hive-swarm/swarm/models/agent.py.v5.bak     hive-swarm/swarm/models/agent.py
mv hive-swarm/swarm/models/config.py.v5.bak    hive-swarm/swarm/models/config.py
mv hive-swarm/swarm/models/state.py.v5.bak     hive-swarm/swarm/models/state.py
mv ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py.v5.bak \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py
mv ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py.v5.bak \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py
rm hive-swarm/swarm/llm/embeddings.py
rm swarm-shared/swarm_shared/pricing.py
rm swarm-shared/tests/test_pricing.py
rm hive-swarm/tests/test_v6_*.py
rm ai-provider-swarm-gateway/tests/test_v6_*.py
```

## Acceptance checklist

- [ ] All v6 file copies done
- [ ] `pytest swarm-shared/tests/test_pricing.py -q` → green
- [ ] `pytest hive-swarm/tests/test_v6_*.py -q` → green
- [ ] `pytest ai-provider-swarm-gateway/tests/test_v6_*.py -q` → green
- [ ] `pytest hive-swarm/tests -q` → green (full regression)
- [ ] `pytest ai-provider-swarm-gateway/tests -q` → green (full regression)
- [ ] `python smoke_test.py` → identical to pre-v6
- [ ] Tier-3 swarm with `--anti-drift off` completes in 1 iteration
- [ ] Tier-3 swarm with `--stream` reports `streamed=True` in JSON
- [ ] `quota show --since 1h` filters as expected
- [ ] `quota show` (empty) prints `[no usage recorded yet]`
- [ ] `route` (missing gateway) prints `Vendor them into...`
