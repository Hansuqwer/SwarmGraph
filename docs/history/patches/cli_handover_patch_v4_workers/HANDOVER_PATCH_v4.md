# Handover patch v4 — wire hive workers through the gateway

## Apply

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# 1) New package
mkdir -p hive-swarm/swarm/llm
cp cli_handover_patch_v4_workers/hive-swarm/swarm/llm/__init__.py \
   cli_handover_patch_v4_workers/hive-swarm/swarm/llm/dispatch.py \
   cli_handover_patch_v4_workers/hive-swarm/swarm/llm/prompts.py \
   hive-swarm/swarm/llm/

# 2) Modified files (back up first if you have local edits)
cp hive-swarm/swarm/nodes/worker.py   hive-swarm/swarm/nodes/worker.py.v3.bak
cp hive-swarm/swarm/nodes/queen.py    hive-swarm/swarm/nodes/queen.py.v3.bak
cp hive-swarm/swarm/models/config.py  hive-swarm/swarm/models/config.py.v3.bak

cp cli_handover_patch_v4_workers/hive-swarm/swarm/nodes/worker.py   hive-swarm/swarm/nodes/worker.py
cp cli_handover_patch_v4_workers/hive-swarm/swarm/nodes/queen.py    hive-swarm/swarm/nodes/queen.py
cp cli_handover_patch_v4_workers/hive-swarm/swarm/models/config.py  hive-swarm/swarm/models/config.py

# 3) Tests
cp cli_handover_patch_v4_workers/hive-swarm/tests/test_llm_dispatch.py \
   cli_handover_patch_v4_workers/hive-swarm/tests/test_worker_gateway.py \
   hive-swarm/tests/

# No re-install needed (editable install picks up the new files)
```

## Verify

```bash
source .venv/bin/activate

# 1) New unit tests
pytest hive-swarm/tests/test_llm_dispatch.py -q
# expected: ~40 passed

pytest hive-swarm/tests/test_worker_gateway.py -q
# expected: ~12 passed

# 2) Full hive regression
pytest hive-swarm/tests -q
# expected: still green; the existing test_models / test_consensus / etc. unchanged

# 3) Gateway regression (proves we didn't break anything on that side)
pytest ai-provider-swarm-gateway/tests/test_cli.py -q
pytest ai-provider-swarm-gateway/tests/test_cli_route.py -q
pytest ai-provider-swarm-gateway/tests/test_quota_atomic.py -q
pytest ai-provider-swarm-gateway/tests/test_nine_router_adapter.py -q
pytest ai-provider-swarm-gateway/tests/test_nine_router_route_integration.py -q

# 4) Stub-mode smoke (must match pre-v4 output exactly)
.venv/bin/python smoke_test.py

# 5) Live gateway smoke — workers go through 9router
AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL=http://localhost:20128/v1 \
AI_PROVIDER_GATEWAY_9ROUTER_MODEL=kc/kilo-auto/free \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
HIVE_SWARM_LLM_BACKEND=gateway \
.venv/bin/python smoke_test.py
# expected: same hive-swarm machinery, but final_output now contains real LLM text
```

## Configuration knobs

### Via Python
```python
from swarm import SwarmConfig, SwarmState, build_swarm_graph

config = SwarmConfig(
    topology="hierarchical",
    consensus_protocol="raft",
    max_agents=5,
    sona_enabled=True,
    # NEW v4 fields:
    llm_backend="gateway",                      # "stub" (default) | "gateway"
    llm_default_provider="9router",             # any registered adapter id
    llm_max_tokens=512,
    llm_temperature=0.0,
    llm_timeout_seconds=60.0,
    llm_include_retrieved_patterns=True,        # SONA → user prompt
    llm_include_objective=True,
    llm_role_provider_overrides={               # per-role overrides
        "coder": "openrouter",
        "security": "anthropic",
    },
)
```

### Via env vars (highest precedence)
```bash
HIVE_SWARM_LLM_BACKEND=gateway        # forces gateway even if config says stub
HIVE_SWARM_LLM_PROVIDER=deepseek      # overrides llm_default_provider
HIVE_SWARM_LLM_MAX_TOKENS=1024
HIVE_SWARM_LLM_TEMPERATURE=0.7
```

Plus the **gateway-side** env vars (unchanged):
```bash
AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL=http://localhost:20128/v1
AI_PROVIDER_GATEWAY_9ROUTER_MODEL=kc/kilo-auto/free
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key>
# or any of the aliases: ROUTER_API_KEY / NINEROUTER_API_KEY /
# KILO_CODE_API_KEY / OPENAI_API_KEY
```

## Architecture (one diagram)

```
SwarmConfig(llm_backend="gateway", ...)
        │
        ▼
queen_node ── _llm_settings_from_config(swarm.config)
        │       creates: {backend, default_provider, max_tokens,
        │                 temperature, timeout, role_overrides,
        │                 include_retrieved_patterns, include_objective}
        ▼
QueenDirective.shared_context["llm_settings"] = {...}
        │
        ▼
Send("worker_node", AgentState{..., task_context: directive.dump()})
        │
        ▼
worker_node:
  settings = resolve_llm_settings(task_context, role)
             # env overrides queen overrides defaults
  dispatcher = build_dispatcher(settings)
        │
        ├─→ StubDispatcher.dispatch(role, desc, ctx)        ← back-compat
        │       returns "[CODER] Implementation for: ..."
        │
        └─→ GatewayDispatcher.dispatch(role, desc, ctx)
              user_prompt = _build_user_prompt(desc, ctx)
                  + retrieved_patterns from ctx (F-27A)
                  + overall objective
              system_prompt = get_system_prompt(role)   # role-specific persona
              adapter = _get_adapter("9router")           # cached
              resp = adapter.chat(messages=[sys, user], ...)
              text = _extract_text(resp)                   # 4-shape tolerant
              return text
        │
        ▼
WorkerResult(success=True, output=<text>, metadata={"llm_backend":..., "llm_provider":...})
        │
        ▼
return {"worker_results": [result.model_dump(mode="json")]}   # F-13A reducer
        │
        ▼
collect_results_node → consensus_node → judge_node → distill → END
```

## What's preserved (regression matrix)

| Concern | Status |
|---|---|
| `SwarmConfig()` with no args ⇒ stub mode | ✅ default `llm_backend="stub"` |
| Stub strings match pre-v4 (`"[CODER] Implementation for: ..."`) | ✅ identical templates |
| `worker_node` return shape `{"worker_results": [...]}` | ✅ unchanged (F-13A reducer still works) |
| `WorkerResult.success`/`error_message` invariant | ✅ enforced |
| Queen Send fan-out with `objective_hash` propagation | ✅ unchanged |
| F-27A retrieved-patterns flow | ✅ now actually reaches the LLM (was state-only before) |
| F-13A operator.add reducer | ✅ unchanged |
| Anti-drift `objective_hash` end-to-end | ✅ unchanged |

## What's new

| Capability | How |
|---|---|
| Real LLM calls in workers | `SwarmConfig(llm_backend="gateway")` or `HIVE_SWARM_LLM_BACKEND=gateway` |
| Per-role provider routing | `llm_role_provider_overrides={"coder": "anthropic", ...}` |
| Role-specific system prompts | `swarm/llm/prompts.py` — edit one file |
| SONA patterns reach the LLM user-prompt | `llm_include_retrieved_patterns=True` (default) |
| Adapter method-name fallback | tries `chat → chat_completion → complete → call → invoke` |
| Response shape tolerance | handles `NineRouterResponse`, `GatewayResponse`, OpenAI dict, plain str |
| Errors stay typed | `WorkerLLMError` → `WorkerResult(success=False, error_message="llm_error: ...")` |

## What's intentionally NOT done in v4

- **Tier 2 medium_agent_node** still emits the stub `[MEDIUM] ...` string. The
  queen→worker path wasn't the right insertion point; tier 2 is a separate
  graph node. Could be a v5 patch or you can just route tier-2 through the
  gateway directly with ~10 LoC.
- **Streaming**. The dispatcher returns a string. Adding a `dispatch_stream`
  method that yields chunks is straightforward (the `data: [DONE]` quirk
  parser is already in `nine_router_adapter.py`); deferred to keep this
  patch surgical.
- **Per-role model overrides** (different model id, same provider). Currently
  per-role override is provider-level. Adding `llm_role_model_overrides`
  alongside is a 5-line change.
- **Telemetry / token counting**. The fields `WorkerResult.metadata` records
  `llm_backend` + `llm_provider`. Token counts from adapter responses (e.g.
  `NineRouterResponse.input_tokens`) are not yet propagated; needs a
  `WorkerResult.usage: TokenUsage | None` field. Defer until needed.

## Rollback

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched
mv hive-swarm/swarm/nodes/worker.py.v3.bak  hive-swarm/swarm/nodes/worker.py
mv hive-swarm/swarm/nodes/queen.py.v3.bak   hive-swarm/swarm/nodes/queen.py
mv hive-swarm/swarm/models/config.py.v3.bak hive-swarm/swarm/models/config.py
rm -rf hive-swarm/swarm/llm/
rm hive-swarm/tests/test_llm_dispatch.py hive-swarm/tests/test_worker_gateway.py
```

## What I need from you to wire it together

1. Apply the file copies above.
2. Run the four `pytest` invocations + the two smokes.
3. Tell me:
   - Anything red in the test output.
   - Whether the live smoke (#5) actually surfaces real LLM text in
     `final.final_output` (it should — that's the point).
   - Whether `_get_adapter("9router")` import resolves cleanly when called
     from inside `swarm.llm.dispatch` (you might need to add `swarm-shared`
     or `ai-provider-swarm-gateway` to a sibling-import path; should work
     fine since both are editable-installed in the same venv).

If any test fails because of upstream graph-version drift on the gateway
side (e.g. `_get_adapter` lives elsewhere now), the dispatcher's
`adapter_factory` constructor parameter is the surgical-fix point — pass a
custom factory that knows your local layout.

## Acceptance checklist

- [ ] `swarm/llm/` package files copied (3 files)
- [ ] `nodes/worker.py`, `nodes/queen.py`, `models/config.py` replaced
- [ ] Two new test files copied
- [ ] `pytest hive-swarm/tests/test_llm_dispatch.py -q` → green
- [ ] `pytest hive-swarm/tests/test_worker_gateway.py -q` → green
- [ ] `pytest hive-swarm/tests -q` → green (full regression)
- [ ] `pytest ai-provider-swarm-gateway/tests -q` → green (full regression)
- [ ] `python smoke_test.py` → pre-v4 output (stub mode preserved)
- [ ] `HIVE_SWARM_LLM_BACKEND=gateway python smoke_test.py` → real LLM text in final_output
