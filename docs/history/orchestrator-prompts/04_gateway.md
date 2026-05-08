# 🐝 Patch v4 — Wire hive workers through the gateway

## Mission
Replace the deterministic stubs in `hive-swarm/swarm/nodes/worker.py:_ROLE_DISPATCH`
with **real LLM calls** routed through the working `ai-provider-swarm-gateway`
adapter dispatch (`graph/nodes._get_adapter`). Default provider: `9router`
(local, free, OpenAI-compatible — already proven end-to-end in milestone
2026-05-07).

## Hard rules

1. **Backwards compatible by default.** A `SwarmConfig()` constructed with no
   arguments behaves exactly as before — stub responses, no network calls.
   Real LLM dispatch is opt-in via `llm_backend="gateway"` config OR the
   `HIVE_SWARM_LLM_BACKEND=gateway` env var.
2. **No breaking changes to the worker return shape.** Still returns
   `{"worker_results": [WorkerResult(...).model_dump(mode="json")]}` so the
   `Annotated[list, operator.add]` reducer (F-13A) keeps working.
3. **No new top-level deps.** Reuse `ai-provider-swarm-gateway` (already
   installed) for adapter dispatch. The `swarm/llm/` package adds zero new
   pip requirements.
4. **Preserve every local fix.** Do not regress: Pydantic validator recursion,
   memory cap, router complexity score, mock SONA distill, LangGraph queen
   alias.
5. **SONA-retrieved patterns must reach the LLM.** When `memory_retrieve_node`
   surfaces patterns, the GatewayDispatcher must include them in the
   user-prompt so they actually influence outputs. Closes F-27A end-to-end.
6. **All errors become typed `WorkerResult(success=False)`.** No bare
   exceptions escape `worker_node` — preserves the consensus protocol's
   ability to count failures.

## Hive Orchestrator role assignments (v4 dispatch)

| Agent | Layer | Owns |
|---|---|---|
| **A16** Worker-Node Patcher | C | `swarm/nodes/worker.py` (rewrite call site, keep stubs as fallback) |
| **A15** Queen-Node Patcher | C | `swarm/nodes/queen.py` (forward `llm_settings` into `shared_context`) |
| **A10** Config Patcher | B | `swarm/models/config.py` (add 6 `llm_*` fields) |
| **A27** SONA Loop Patcher | E | verify retrieved_patterns flow through queen → worker → dispatcher → user prompt |
| **A29** Provider/Quota Patcher | F | confirm `_get_adapter("9router")` returns a configured `NineRouterAdapter` when env vars are set |
| **A04** Test-Strategy Auditor | A | new tests cover: stub parity, gateway path mocked, error mapping, env override, retrieved-patterns injection |
| **A05** Anti-Drift Sentinel | A | confirm objective_hash still preserved; no out-of-scope edits |

## Deliverables in this patch (`cli_handover_patch_v4_workers/`)

```
hive-swarm/
├── swarm/
│   ├── llm/
│   │   ├── __init__.py                 ← public API
│   │   ├── prompts.py                  ← role-specific system prompts
│   │   └── dispatch.py                 ← StubDispatcher + GatewayDispatcher
│   ├── nodes/
│   │   ├── worker.py                   ← MODIFIED (full file)
│   │   └── queen.py                    ← MODIFIED (full file, llm_settings forwarding)
│   └── models/
│       └── config.py                   ← MODIFIED (full file, +6 llm_* fields)
└── tests/
    ├── test_llm_dispatch.py            ← NEW
    └── test_worker_gateway.py          ← NEW
HIVE_TO_GATEWAY_PROMPT.md               ← this prompt
HANDOVER_PATCH_v4.md                    ← apply / verify / rollback
```

## How it composes

```
SwarmConfig(llm_backend="gateway", llm_default_provider="9router")
        ↓
queen_node forwards config-derived llm_settings into QueenDirective.shared_context
        ↓
Send → worker_node receives AgentState with task_context["shared_context"]["llm_settings"]
        ↓
worker_node calls _build_dispatcher(settings) → GatewayDispatcher
        ↓
GatewayDispatcher._ensure_adapter() lazy-imports
   ai_provider_swarm_gateway.graph.nodes._get_adapter("9router")
        ↓
adapter.chat(messages=[system, user], max_tokens=..., temperature=...)
   - system prompt: role-specific persona from swarm/llm/prompts.py
   - user prompt: task_description + retrieved_patterns + objective context
        ↓
_extract_text(response) handles every shape:
   NineRouterResponse / GatewayResponse / OpenAI-dict / plain str
        ↓
WorkerResult(success=True, output=<llm text>, ...) flows into reducer
```

## Acceptance criteria

| # | Criterion |
|---|---|
| 1 | `pytest hive-swarm/tests/test_llm_dispatch.py -q` → green |
| 2 | `pytest hive-swarm/tests/test_worker_gateway.py -q` → green |
| 3 | `pytest hive-swarm/tests -q` (full regression) → green |
| 4 | `python smoke_test.py` (existing stub-mode test) → identical output as before |
| 5 | `HIVE_SWARM_LLM_BACKEND=gateway python smoke_test.py` → workers return real text from 9router |
| 6 | All 5 gateway tests still green (no regression on the gateway side) |
| 7 | Anti-drift sentinel signs off: `objective_hash` preserved end-to-end |

## Stop signal

```
✅ HIVE WORKERS WIRED THROUGH GATEWAY
   Default behaviour preserved (stub mode)
   Opt-in gateway mode: env or config flag
   SONA-retrieved patterns reach LLM user-prompt
   All test suites green
   Live smoke: ai-provider-gateway → 9router → real swarm output
```

— end of prompt —
