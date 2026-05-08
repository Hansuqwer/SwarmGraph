# 🐝 Patch v7 — Canonicalization + real embedder + interactive HITL + multi-tenant quota

## Mission

Ship one patch with two concerns:

### Part A — Canonicalization (your 6 v6.1 fixes, properly named and tested)

| Local fix | New canonical name | Where |
|---|---|---|
| `worker_results` dedupe-merge | **F-13A-CORR1** | `swarm/graphs/factory.py` (custom reducer) |
| Rich markup escape for quota messages | **F-30-COSM1** | `cli.py` (escape `[...]` via `\[`) |
| Embedding threshold=0 → mode-off coalesce | **F-18-CORR2** | `swarm/models/state.py::_check_drift_embedding` |
| Queen forwards `stream_enabled` + `cost_tracking_enabled` | **F-15-FWD1** | `swarm/nodes/queen.py::_llm_settings_from_config` |
| `HIVE_SWARM_COST_TRACKING` env var | **F-17-ENV1** | `swarm/llm/dispatch.py::resolve_llm_settings` |
| `NineRouterAdapter.call() → GatewayResponse` | **F-29-RET1** | `nine_router_adapter.py::call` |

### Part B — Three new features

1. **Real OpenAI embeddings adapter** (`OpenAIEmbeddingAdapter`)
   — backs `set_default_embedder()` with `text-embedding-3-small` for real
   semantic anti-drift. Falls back to `HashEmbedder` when no key.

2. **Interactive HITL** in `ai-provider-gateway swarm` — TTY-detecting
   prompt with single-use `decision_token` echo. Non-TTY runs preserve
   v5/v6 auto-approve behaviour.

3. **Multi-tenant quota isolation** — `tenant_id` parameter (env var
   `AI_PROVIDER_GATEWAY_TENANT`); separate `usage.json` per tenant under
   `~/.ai_provider_gateway/tenants/<tenant_id>/usage.json`.

## Hard rules

1. **Backwards compatible by default.** No-arg `SwarmConfig()` unchanged.
   Single-tenant runs (no env var) use the existing `usage.json` path.
   Non-TTY HITL behaviour preserved.
2. **No new top-level deps.** OpenAI embeddings via `urllib.request`
   (same pattern as `NineRouterAdapter`); HITL via stdlib `sys.stdin.isatty()`.
3. **All errors typed.** Embedder failures → `[]` → keyword fallback.
   HITL deny → `failure_cause="approval_denied"`.
4. **Anti-drift sentinel guards scope.** Pure additive; no graph rewrites.

## Hive Orchestrator role assignments (v7 dispatch)

| Agent | Layer | Owns |
|---|---|---|
| **A13** Graph-Factory | C | F-13A-CORR1: dedupe reducer in `factory.py` |
| **A18** Judge / Anti-Drift | C | F-18-CORR2: threshold=0 coalesce in `state.py` |
| **A30** Gateway CLI | F | F-30-COSM1: Rich-escape; HITL UX; multi-tenant flag |
| **A15** Queen-Node | C | F-15-FWD1: stream + cost forwarding in queen |
| **A17** Dispatcher | C | F-17-ENV1: cost env var resolution |
| **A29** Provider Adapter | F | F-29-RET1: `call()→GatewayResponse`; OpenAI embedder adapter |
| **A12** Embedding | E | `OpenAIEmbeddingAdapter` in `swarm/llm/embeddings.py` |
| **A19** Approval / HITL | C | TTY-aware approval prompt in CLI; preserves single-use guard |
| **A26** Quota | E | Multi-tenant `QuotaTracker` factory; per-tenant storage path |
| **A04** Test-Strategy | A | regression tests for every canonical fix + feature tests |
| **A05** Anti-Drift Sentinel | A | sign off objective_hash; no scope creep |

## Deliverables (`cli_handover_patch_v7/`)

```
swarm-shared/
└── (no changes — pricing module is fine as-is)

hive-swarm/
├── swarm/
│   ├── llm/
│   │   ├── dispatch.py                 ← MODIFIED (F-17-ENV1 + cost env var)
│   │   └── embeddings.py               ← MODIFIED (OpenAIEmbeddingAdapter added)
│   ├── nodes/
│   │   └── queen.py                    ← MODIFIED (F-15-FWD1: forward stream + cost)
│   ├── models/
│   │   └── state.py                    ← MODIFIED (F-18-CORR2: threshold=0 coalesce)
│   └── graphs/
│       └── factory.py                  ← MODIFIED (F-13A-CORR1: dedupe reducer)
└── tests/
    ├── test_v7_canonicalization.py     ← NEW (regression for all 6 canon fixes)
    ├── test_v7_openai_embeddings.py    ← NEW (mocked HTTP)
    └── test_v7_multi_tenant_quota.py   ← NEW

ai-provider-swarm-gateway/
├── src/ai_provider_swarm_gateway/
│   ├── cli.py                          ← MODIFIED (F-30-COSM1 + --tenant + interactive HITL)
│   ├── providers/
│   │   └── nine_router_adapter.py      ← MODIFIED (F-29-RET1: call() canonical)
│   └── quota/
│       └── tracker.py                  ← MODIFIED (multi-tenant factory)
└── tests/
    ├── test_v7_hitl_interactive.py     ← NEW (mocked stdin)
    └── test_v7_tenant_isolation.py     ← NEW

HIVE_V7_PROMPT.md                       ← this prompt
HANDOVER_PATCH_v7.md                    ← apply / verify / rollback
```

## Acceptance criteria

| # | Criterion |
|---|---|
| 1 | All 6 canonical fixes pass regression tests in `test_v7_canonicalization.py` |
| 2 | `pytest hive-swarm/tests -q` → green (full regression) |
| 3 | `pytest ai-provider-swarm-gateway/tests -q` → green (full regression) |
| 4 | Tier-3 swarm with retry: `worker_count` exactly equals one iteration's fan-out (NOT N×fan-out) |
| 5 | `OpenAIEmbeddingAdapter` used when `OPENAI_API_KEY` set; `HashEmbedder` fallback otherwise |
| 6 | `ai-provider-gateway swarm --interactive` (or auto-detect TTY) prompts on high-risk consensus |
| 7 | `AI_PROVIDER_GATEWAY_TENANT=alice` writes to `~/.ai_provider_gateway/tenants/alice/usage.json` |
| 8 | `quota show` empty case renders the canonical message (no Rich-markup swallowing) |

## Stop signal

```
✅ HIVE V7 SHIPPED
   6 canonical fixes (F-13A-CORR1, F-30-COSM1, F-18-CORR2, F-15-FWD1, F-17-ENV1, F-29-RET1)
   OpenAI embeddings adapter (real semantic drift detection)
   Interactive HITL (TTY-aware, single-use token preserved)
   Multi-tenant quota isolation
   All test suites green
   Stub mode + single-tenant + non-TTY paths preserved
```

— end of prompt —
