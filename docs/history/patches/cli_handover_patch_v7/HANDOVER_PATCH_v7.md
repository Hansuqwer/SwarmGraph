# Handover patch v7 — Canonicalization + OpenAI embedder + interactive HITL + multi-tenant quota

> **One bundle, two concerns:** Part A canonizes your six v6.1-era local
> fixes (so future patches don't re-introduce the bugs), Part B ships
> three new features that build on the now-canonical surface.

## File map

| File | Role | Change kind |
|---|---|---|
| `hive-swarm/swarm/graphs/factory.py` | F-13A-CORR1: dedupe-merge reducer | MODIFIED |
| `hive-swarm/swarm/models/state.py` | F-18-CORR2: threshold=0 → mode-off coalesce | MODIFIED |
| `hive-swarm/swarm/nodes/queen.py` | F-15-FWD1: forward stream + cost into llm_settings | MODIFIED |
| `hive-swarm/swarm/llm/dispatch.py` | F-17-ENV1: HIVE_SWARM_COST_TRACKING env | MODIFIED |
| `hive-swarm/swarm/llm/embeddings.py` | OpenAIEmbeddingAdapter + default_embedder_from_env | MODIFIED |
| `hive-swarm/swarm/llm/__init__.py` | re-export OpenAI adapter + helper | MODIFIED |
| `ai-provider-swarm-gateway/src/.../providers/nine_router_adapter.py` | F-29-RET1: call() → GatewayResponse | MODIFIED |
| `ai-provider-swarm-gateway/src/.../quota/tracker.py` | multi-tenant isolation | MODIFIED |
| `ai-provider-swarm-gateway/src/.../cli.py` | F-30-COSM1 + --tenant + interactive HITL | MODIFIED |
| `hive-swarm/tests/test_v7_canonicalization.py` | regression for all 6 canon fixes | NEW |
| `hive-swarm/tests/test_v7_openai_embeddings.py` | mocked HTTP | NEW |
| `hive-swarm/tests/test_v7_multi_tenant_quota.py` | tenant isolation (lives in hive tests because it imports the tracker) | NEW |
| `ai-provider-swarm-gateway/tests/test_v7_hitl_interactive.py` | mocked stdin | NEW |
| `ai-provider-swarm-gateway/tests/test_v7_tenant_isolation.py` | end-to-end CLI | NEW |

## Apply

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# Back up everything v7 modifies
for f in hive-swarm/swarm/graphs/factory.py \
         hive-swarm/swarm/models/state.py \
         hive-swarm/swarm/nodes/queen.py \
         hive-swarm/swarm/llm/dispatch.py \
         hive-swarm/swarm/llm/embeddings.py \
         hive-swarm/swarm/llm/__init__.py \
         ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py \
         ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py \
         ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py
do
  cp "$f" "$f.v6.bak"
done

# --- hive-swarm ---
cp cli_handover_patch_v7/hive-swarm/swarm/graphs/factory.py    hive-swarm/swarm/graphs/
cp cli_handover_patch_v7/hive-swarm/swarm/models/state.py      hive-swarm/swarm/models/
cp cli_handover_patch_v7/hive-swarm/swarm/nodes/queen.py       hive-swarm/swarm/nodes/
cp cli_handover_patch_v7/hive-swarm/swarm/llm/dispatch.py      hive-swarm/swarm/llm/
cp cli_handover_patch_v7/hive-swarm/swarm/llm/embeddings.py    hive-swarm/swarm/llm/
cp cli_handover_patch_v7/hive-swarm/swarm/llm/__init__.py      hive-swarm/swarm/llm/
cp cli_handover_patch_v7/hive-swarm/tests/test_v7_*.py         hive-swarm/tests/

# --- gateway ---
cp cli_handover_patch_v7/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/
cp cli_handover_patch_v7/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/
cp cli_handover_patch_v7/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/
cp cli_handover_patch_v7/ai-provider-swarm-gateway/tests/test_v7_*.py \
   ai-provider-swarm-gateway/tests/
```

## Verify

```bash
source .venv/bin/activate

# Canonicalization regression (all 6 fixes)
pytest hive-swarm/tests/test_v7_canonicalization.py -q

# v7 features
pytest hive-swarm/tests/test_v7_openai_embeddings.py -q
pytest hive-swarm/tests/test_v7_multi_tenant_quota.py -q
pytest ai-provider-swarm-gateway/tests/test_v7_hitl_interactive.py -q
pytest ai-provider-swarm-gateway/tests/test_v7_tenant_isolation.py -q

# Full regression
pytest swarm-shared/tests -q
pytest hive-swarm/tests -q
pytest ai-provider-swarm-gateway/tests -q

# Stub mode unchanged
.venv/bin/python smoke_test.py

# The 80-vs-5 fix proven: no retry storm even on 16 iterations
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
ai-provider-gateway swarm \
  --prompt "implement comprehensive distributed authentication architecture" \
  --backend gateway --provider 9router --model kc/kilo-auto/free \
  --anti-drift off --max-agents 5 --json --show-workers
# expected: worker_count=5 (NOT 80), iterations=1, total_cost_usd=0

# Multi-tenant isolation
ai-provider-gateway quota increment --provider openai --requests 5 --tenant alice
ai-provider-gateway quota increment --provider openai --requests 1 --tenant bob
ai-provider-gateway quota show --tenant alice    # 5 requests
ai-provider-gateway quota show --tenant bob      # 1 request
ai-provider-gateway tenants list                  # alice + bob
ls ~/.ai_provider_gateway/tenants/                # alice/ bob/

# Interactive HITL
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
ai-provider-gateway swarm \
  --prompt "delete all production data" \
  --backend gateway --provider 9router --model kc/kilo-auto/free \
  --no-auto-approve --interactive
# expected: prompts you to approve/deny; respects single-use token

# OpenAI embeddings (real semantic anti-drift)
OPENAI_API_KEY=<your-real-key> \
ai-provider-gateway swarm \
  --prompt "..." \
  --anti-drift embedding   # uses OpenAIEmbeddingAdapter automatically
```

> Setting up `OPENAI_API_KEY` makes `default_embedder_from_env()` return
> `OpenAIEmbeddingAdapter()`. Without it, `HashEmbedder` is used (deterministic,
> no network — fine for tests but bag-of-words only).

## What v7 changes

### Part A — 6 canonical fixes

| ID | Was | Now |
|---|---|---|
| **F-13A-CORR1** | `Annotated[list, operator.add]` doubled `worker_results` on retry replay → 80 entries from 5 workers | `_merge_worker_results` deduplicates by `(agent_id, task_id)` → idempotent under replay |
| **F-30-COSM1** | `_console.print("[no usage recorded yet]")` was eaten as Rich markup → empty output | `_print_plain` uses `rich.markup.escape` so brackets render verbatim |
| **F-18-CORR2** | `threshold=0` + `mode="embedding"` always passed via `cosine ≥ 0`, semantically meaningless | `check_drift` short-circuits when `threshold == 0` → consistent with mode="off" |
| **F-15-FWD1** | Queen's `_llm_settings_from_config` missed `stream_enabled` + `cost_tracking_enabled` | now forwards both fields explicitly |
| **F-17-ENV1** | No env var for cost tracking (asymmetric with `HIVE_SWARM_LLM_STREAM`) | `HIVE_SWARM_COST_TRACKING` honoured (true/false/0/1/yes/no/on/off) |
| **F-29-RET1** | `NineRouterAdapter.call()` returned `NineRouterResponse` → `provider_call_node` couldn't validate | returns upstream `GatewayResponse` (defensive: falls back to NineRouterResponse if model missing) |

### Part B — Three new features

#### 1. OpenAIEmbeddingAdapter

```python
from swarm.llm.embeddings import OpenAIEmbeddingAdapter, set_default_embedder

# Explicit
set_default_embedder(OpenAIEmbeddingAdapter())   # reads OPENAI_API_KEY

# Auto-pick best available
from swarm.llm.embeddings import default_embedder_from_env
set_default_embedder(default_embedder_from_env())   # OpenAI if key set, HashEmbedder otherwise

# Use with anti-drift
config = SwarmConfig(
    anti_drift_mode="embedding",
    anti_drift_similarity_threshold=0.5,
)
```

API key resolved from any of:
- `OPENAI_API_KEY` (primary)
- `OPENAI_EMBEDDINGS_API_KEY`
- `AI_PROVIDER_OPENAI_API_KEY`

Failure modes (no key, network error, malformed response, missing field) all
return `[]` so `SwarmState._check_drift_embedding` falls back to keyword
detection. Never raises.

#### 2. Interactive HITL

```bash
ai-provider-gateway swarm --prompt "..." --no-auto-approve --interactive
```

When stdin is a TTY (or `--interactive` explicit), the CLI prompts on
high-risk consensus rounds:

```
HITL approval required — swarm=cli-abc123
protocol=raft  agreement=0.4  risk=0.6
┌─ Proposed action ────────────────────────────────────────┐
│ delete all production data                               │
└──────────────────────────────────────────────────────────┘
token=a1b2c3d4…
Approve this action? (y/n): _
```

The decision token is **echoed verbatim** to preserve the F-19A single-use
guard. Reviewer ID resolved from `AI_PROVIDER_GATEWAY_REVIEWER_ID` →
`USER` → `"cli"`.

Non-TTY runs (CI, pipes) preserve v5/v6 auto-approve behaviour unchanged.

#### 3. Multi-tenant quota isolation

```bash
# Per-tenant via flag
ai-provider-gateway quota increment --provider openai --requests 5 --tenant alice

# Or via env (sticky for the process)
export AI_PROVIDER_GATEWAY_TENANT=alice
ai-provider-gateway quota show
ai-provider-gateway swarm --prompt "..."   # all quota writes go to alice/

# Inspection
ai-provider-gateway tenants list
ai-provider-gateway tenants storage-path alice
```

Storage layout:
```
~/.ai_provider_gateway/
├── usage.json                     # single-tenant default (back-compat)
└── tenants/
    ├── alice/usage.json
    ├── bob/usage.json
    └── team_alpha/usage.json
```

Tenant ids validated against `[a-zA-Z0-9_-]{1,64}` — path traversal blocked
at construction time.

## What's preserved (regression matrix)

| Concern | Status |
|---|---|
| `SwarmConfig()` no-arg → stub mode, no LLM, no embeddings | ✅ |
| `WorkerResult.usage.cost_usd = None` for unknown models | ✅ |
| Reducer-friendly worker return shape | ✅ |
| F-07-CORR3 vote truncation | ✅ |
| F-15-LG4 queen Send fan-out | ✅ |
| F-13A reducer registered | ✅ (now via F-13A-CORR1 dedupe-merge) |
| F-27A SONA-loop closure | ✅ |
| Anti-drift `objective_hash` end-to-end | ✅ |
| Single-tenant default quota path | ✅ (when no `--tenant` and no env var) |
| Non-TTY swarm runs auto-approve | ✅ (preserves v5/v6 behaviour) |

## Rollback

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched
for f in hive-swarm/swarm/graphs/factory.py \
         hive-swarm/swarm/models/state.py \
         hive-swarm/swarm/nodes/queen.py \
         hive-swarm/swarm/llm/dispatch.py \
         hive-swarm/swarm/llm/embeddings.py \
         hive-swarm/swarm/llm/__init__.py \
         ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py \
         ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/quota/tracker.py \
         ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py
do
  mv "$f.v6.bak" "$f"
done
rm hive-swarm/tests/test_v7_*.py
rm ai-provider-swarm-gateway/tests/test_v7_*.py
```

## Acceptance checklist

- [ ] All file copies done (9 modified + 5 new tests)
- [ ] `pytest hive-swarm/tests/test_v7_canonicalization.py -q` → green (regresses each canon fix)
- [ ] `pytest hive-swarm/tests/test_v7_*.py -q` → green
- [ ] `pytest ai-provider-swarm-gateway/tests/test_v7_*.py -q` → green
- [ ] Full regression: `pytest hive-swarm/tests -q` and `pytest ai-provider-swarm-gateway/tests -q` both green
- [ ] `python smoke_test.py` → identical to pre-v7 stub output
- [ ] Tier-3 swarm with `--anti-drift off` returns `worker_count=5` (NOT 80)
- [ ] `quota show` empty case prints `[no usage recorded yet]` literally (no Rich swallow)
- [ ] Two-tenant isolation: `--tenant alice` and `--tenant bob` see only their own counters
- [ ] `--interactive` on a TTY prompts; piped runs auto-approve
- [ ] `OPENAI_API_KEY=<...> --anti-drift embedding` uses real embeddings
