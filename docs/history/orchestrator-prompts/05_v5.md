# 🐝 Patch v5 — Tier-2 + per-role models + token usage + swarm CLI

## Mission

Five **purely additive** features. Zero structural fixes — the stack is operationally
complete after v4 + your two upstream-bound fixes (F-15-LG4, F-07-CORR3). v5 is
about exposing what's there and adding ergonomics:

1. **Tier-2 through gateway** — `medium_agent_node` calls the LLM (was a stub).
2. **Per-role model overrides** — `llm_role_model_overrides={"coder": "anthropic/claude-opus-4-7"}`
   alongside the existing `llm_role_provider_overrides`.
3. **Token usage propagation** — `WorkerResult.usage: TokenUsage | None` populated
   from adapter responses; `TokenUsage` model added.
4. **`ai-provider-gateway swarm` CLI subcommand** — single command to route a
   prompt through the full hive-swarm with the gateway underneath.
5. **Tier-3 smoke test** — `smoke_test_tier3.py` with a complex objective so
   `HIVE_SWARM_LLM_BACKEND=gateway python smoke_test_tier3.py` actually
   exercises the worker→gateway path.

## Hard rules

1. **Backwards compatible by default.** Every new field defaults to current
   behaviour. `WorkerResult.usage = None` when no usage data is available.
   `dispatch()` still returns `str` (Stub + Gateway).
2. **No new top-level deps.** Reuse existing packages.
3. **Stub mode untouched.** `SwarmConfig()` no-arg construction → identical
   pre-v5 behaviour.
4. **All errors stay typed.** `WorkerLLMError` → `WorkerResult(success=False)`.
5. **Anti-drift sentinel guards scope.** No structural rewrites; v4 + the two
   upstream fixes are canon.

## Hive Orchestrator role assignments (v5 dispatch)

| Agent | Layer | Owns |
|---|---|---|
| **A07** Agent-Model Patcher | B | `swarm/models/agent.py` — add `TokenUsage`, `WorkerResult.usage` |
| **A10** Config Patcher | B | `swarm/models/config.py` — add `llm_role_model_overrides` |
| **A15** Queen-Node Patcher | C | `swarm/nodes/queen.py` — `medium_agent_node` through gateway |
| **A16** Worker-Node Patcher | C | `swarm/nodes/worker.py` — consume `dispatch_full`, populate `usage` |
| **A17** Dispatch Author | C | `swarm/llm/dispatch.py` — add `WorkerLLMResponse`, `dispatch_full`, per-role model |
| **A29** Gateway CLI Patcher | F | `cli.py` — new `swarm` subcommand |
| **A04** Test-Strategy Auditor | A | new tests cover all of the above |
| **A05** Anti-Drift Sentinel | A | confirm objective_hash preserved; no scope creep |

## Deliverables in this patch (`cli_handover_patch_v5/`)

```
hive-swarm/
├── swarm/
│   ├── llm/
│   │   └── dispatch.py                 ← MODIFIED (full file)
│   ├── nodes/
│   │   ├── queen.py                    ← MODIFIED (medium_agent_node uses gateway)
│   │   └── worker.py                   ← MODIFIED (consumes dispatch_full, populates usage)
│   └── models/
│       ├── agent.py                    ← MODIFIED (TokenUsage + WorkerResult.usage)
│       └── config.py                   ← MODIFIED (llm_role_model_overrides)
├── tests/
│   ├── test_v5_dispatch_full.py        ← NEW
│   ├── test_v5_token_usage.py          ← NEW
│   └── test_v5_medium_gateway.py       ← NEW
└── smoke_test_tier3.py                 ← NEW

ai-provider-swarm-gateway/
├── src/ai_provider_swarm_gateway/
│   └── cli.py                          ← MODIFIED (full file, adds `swarm` subcommand)
└── tests/
    └── test_cli_swarm.py               ← NEW

HIVE_V5_PROMPT.md                       ← this prompt
HANDOVER_PATCH_v5.md                    ← apply / verify / rollback
```

## Acceptance criteria

| # | Criterion |
|---|---|
| 1 | `pytest hive-swarm/tests/test_v5_*.py -q` → green |
| 2 | `pytest hive-swarm/tests -q` (full regression) → green |
| 3 | `pytest ai-provider-swarm-gateway/tests -q` → green |
| 4 | `python smoke_test.py` → identical pre-v5 output (stub mode preserved) |
| 5 | `HIVE_SWARM_LLM_BACKEND=gateway python smoke_test_tier3.py` → real LLM text in `final_output` + `WorkerResult.usage.input_tokens > 0` |
| 6 | `ai-provider-gateway swarm --prompt "implement add(a,b)" --json` → swarm completes, JSON shows selected providers + final output + token totals |
| 7 | `SwarmConfig(llm_role_model_overrides={"coder": "claude-opus-4-7"})` round-trips through queen → worker → adapter `model=` kwarg |

## What's intentionally deferred to v6

- **Streaming** (`dispatch_stream`, `--stream` flag). The SSE machinery exists in
  `NineRouterAdapter`; wiring it through the swarm requires consensus protocols
  to handle progressive results, which is its own design.
- **Interactive HITL** in the gateway CLI. v5 sets a high default
  `require_approval_above_risk` to suppress HITL for non-interactive runs;
  proper Command(resume=...) UX waits for v6.
- **Cost computation**. `TokenUsage` carries the counts; turning them into $
  requires per-provider pricing tables which belong upstream in the gateway
  registry.

## Stop signal

```
✅ HIVE V5 SHIPPED
   Tier-2 through gateway (medium_agent_node)
   Per-role model overrides
   Token usage propagation (WorkerResult.usage)
   ai-provider-gateway swarm CLI subcommand
   smoke_test_tier3.py exercises worker→gateway path
   All test suites green
   Stub mode preserved bit-for-bit
```

— end of prompt —
