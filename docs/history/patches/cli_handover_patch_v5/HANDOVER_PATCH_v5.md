# Handover patch v5 — Tier-2 + per-role models + token usage + swarm CLI

> Purely additive on top of v4 + your two upstream-bound fixes (F-15-LG4, F-07-CORR3).
> Stub mode unchanged. Gateway mode gains: real Tier-2 LLM, per-role model overrides,
> token-usage propagation, and a single-command CLI surface.

## Apply

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# --- hive-swarm ---
# Modified files: back up first
cp hive-swarm/swarm/llm/__init__.py            hive-swarm/swarm/llm/__init__.py.v4.bak
cp hive-swarm/swarm/llm/dispatch.py            hive-swarm/swarm/llm/dispatch.py.v4.bak
cp hive-swarm/swarm/nodes/worker.py            hive-swarm/swarm/nodes/worker.py.v4.bak
cp hive-swarm/swarm/nodes/queen.py             hive-swarm/swarm/nodes/queen.py.v4.bak
cp hive-swarm/swarm/models/agent.py            hive-swarm/swarm/models/agent.py.v4.bak
cp hive-swarm/swarm/models/config.py           hive-swarm/swarm/models/config.py.v4.bak

cp cli_handover_patch_v5/hive-swarm/swarm/llm/__init__.py     hive-swarm/swarm/llm/__init__.py
cp cli_handover_patch_v5/hive-swarm/swarm/llm/dispatch.py     hive-swarm/swarm/llm/dispatch.py
cp cli_handover_patch_v5/hive-swarm/swarm/nodes/worker.py     hive-swarm/swarm/nodes/worker.py
cp cli_handover_patch_v5/hive-swarm/swarm/nodes/queen.py      hive-swarm/swarm/nodes/queen.py
cp cli_handover_patch_v5/hive-swarm/swarm/models/agent.py     hive-swarm/swarm/models/agent.py
cp cli_handover_patch_v5/hive-swarm/swarm/models/config.py    hive-swarm/swarm/models/config.py

# New files
cp cli_handover_patch_v5/hive-swarm/tests/test_v5_dispatch_full.py   hive-swarm/tests/
cp cli_handover_patch_v5/hive-swarm/tests/test_v5_token_usage.py     hive-swarm/tests/
cp cli_handover_patch_v5/hive-swarm/tests/test_v5_medium_gateway.py  hive-swarm/tests/
cp cli_handover_patch_v5/hive-swarm/smoke_test_tier3.py              hive-swarm/smoke_test_tier3.py

# --- ai-provider-swarm-gateway ---
cp ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py.v4.bak

cp cli_handover_patch_v5/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py
cp cli_handover_patch_v5/ai-provider-swarm-gateway/tests/test_cli_swarm.py \
   ai-provider-swarm-gateway/tests/test_cli_swarm.py

# No re-install needed (editable install picks up the changes)
```

> **Note on your local CLI fixes:** your patched `cli.py` had `quota reset`
> calling `tracker.reset_usage()` (a method you added locally) and `route`
> extracting `routing_decision.selected_provider_id` + `provider_response.content`.
> The v5 `cli.py` preserves both: `reset` checks `hasattr(tracker, "reset_usage")`
> and falls through to `set_reset_time(now)` if not present (back-compat with the
> upstream tracker), and `route`'s `_extract_field` walks the same key list plus
> the new alternates.

## Verify

```bash
source .venv/bin/activate

# v5 hive tests
pytest hive-swarm/tests/test_v5_dispatch_full.py -q     # ~25 passed
pytest hive-swarm/tests/test_v5_token_usage.py -q       # ~13 passed
pytest hive-swarm/tests/test_v5_medium_gateway.py -q    # ~6 passed

# Full hive regression
pytest hive-swarm/tests -q

# v5 gateway test
pytest ai-provider-swarm-gateway/tests/test_cli_swarm.py -q

# Full gateway regression
pytest ai-provider-swarm-gateway/tests -q

# Stub-mode smoke (must match v4 / pre-v5 output)
.venv/bin/python smoke_test.py

# Tier-3 stub smoke (workers fire, deterministic)
.venv/bin/python hive-swarm/smoke_test_tier3.py

# Tier-3 LIVE smoke (real LLM through 9router; needs key)
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL=http://localhost:20128/v1 \
AI_PROVIDER_GATEWAY_9ROUTER_MODEL=kc/kilo-auto/free \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
.venv/bin/python hive-swarm/smoke_test_tier3.py
# expected: per-worker output with real Python code, total_input_tokens > 0,
#           total_output_tokens > 0, final_output non-empty

# CLI single-command swarm (stub mode — no key needed)
ai-provider-gateway swarm --prompt "rename foo to bar"

# CLI swarm (gateway mode — needs 9router up + key)
HIVE_SWARM_LLM_BACKEND=gateway \
AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<key> \
ai-provider-gateway swarm \
    --prompt "implement add(a, b) -> int with type hints and a docstring" \
    --backend gateway --provider 9router \
    --max-agents 3 --show-workers
```

## What v5 adds

### 1. Tier-2 through gateway (`medium_agent_node`)

Before: stub `[MEDIUM] Single-agent result for: ...` regardless of backend.
After: real LLM call when `llm_backend="gateway"`. Single LLM, no swarm spawn —
ideal for medium-complexity tasks where Tier-3 is overkill but stub is too dumb.

```python
config = SwarmConfig(llm_backend="gateway")
state = SwarmState(swarm_id="t2", objective="format this Python code: ...", config=config)
graph = build_swarm_graph(config)
# router → medium_agent_node → real LLM → final_output
```

### 2. Per-role model overrides

```python
config = SwarmConfig(
    llm_backend="gateway",
    llm_default_provider="9router",
    llm_default_model="kc/kilo-auto/free",       # default for everyone
    llm_role_provider_overrides={                # provider per role (v4)
        "security": "anthropic",
    },
    llm_role_model_overrides={                   # model per role (v5 NEW)
        "coder": "anthropic/claude-opus-4-7",
        "tester": "openai/gpt-4o-mini",
        "security": "claude-opus-4-7",
    },
)
```

The dispatcher now passes `model=` to every adapter call. If an adapter's
`chat()` doesn't accept `model=`, the dispatcher silently retries without it
(detected via `TypeError` on the kwarg).

### 3. Token usage propagation

`WorkerResult.usage: TokenUsage | None` populated by gateway-mode workers:

```python
final = SwarmState.from_json_dict(graph.invoke(...))
for r in final.worker_results:
    if r.usage:
        print(f"{r.agent_role}: in={r.usage.input_tokens} out={r.usage.output_tokens} "
              f"model={r.usage.model_id_used}")
```

`collect_results_node` rolls up totals into the consensus history entry:
```python
{"kind": "consensus", "node": "collect_results",
 "vote_count": 5, "worker_count": 5,
 "total_input_tokens": 1240, "total_output_tokens": 380}
```

### 4. `ai-provider-gateway swarm` subcommand

```bash
ai-provider-gateway swarm --prompt "implement add(a,b)" --json
ai-provider-gateway swarm --prompt "..." --backend gateway --provider 9router
ai-provider-gateway swarm --prompt "..." --topology mesh --consensus gossip --max-agents 6
ai-provider-gateway swarm --prompt "..." --show-workers --no-auto-approve
```

Closes the operator surface: one command runs the whole stack.

| Flag | Default | Meaning |
|---|---|---|
| `--prompt -p` | required | The objective for the swarm |
| `--topology` | hierarchical | mesh / ring / star / adaptive |
| `--consensus` | raft | bft / gossip / majority |
| `--max-agents` | 5 | upper bound on parallel workers |
| `--backend` | stub | `gateway` for real LLM |
| `--provider` | 9router | when backend=gateway |
| `--model` | (adapter default) | global model id |
| `--max-tokens` | 512 | per-call cap |
| `--temperature` | 0.0 | sampling |
| `--sona/--no-sona` | sona | enable SONA memory loop |
| `--auto-approve` | on | raises HITL threshold so non-interactive runs complete |
| `--thread-id` | random | LangGraph thread id |
| `--json` | off | machine output (compact one-line JSON) |
| `--show-workers` | off | per-worker breakdown in output |

### 5. `smoke_test_tier3.py`

A complement to the existing `smoke_test.py`. The original lands in tier-1
(fast path); this one's verbose objective lands in tier-3 so workers fire
even with `HIVE_SWARM_LLM_BACKEND=gateway`. Prints token totals + per-worker
breakdown.

## What's preserved (regression matrix)

| Concern | Status |
|---|---|
| `SwarmConfig()` no-arg → stub mode | ✅ defaults unchanged |
| `WorkerResult` invariants (success/error_message) | ✅ |
| `WorkerResult.usage` is **optional** | ✅ stub-mode workers can leave it None or set the stub-metadata variant |
| `dispatch()` returns `str` | ✅ thin wrapper around `dispatch_full` |
| Reducer-friendly worker return shape | ✅ unchanged |
| `to_vote()` truncation (F-07-CORR3) | ✅ preserved |
| Queen Send fan-out (F-15-LG4) | ✅ preserved (your factory.py unchanged) |
| F-13A operator.add reducer | ✅ unchanged |
| F-27A SONA-loop closure | ✅ unchanged |
| Anti-drift `objective_hash` end-to-end | ✅ unchanged |

## What's deferred to v6

- **Streaming** (`dispatch_stream` returning chunks; `--stream` flag).
- **Interactive HITL** in `ai-provider-gateway swarm` (currently auto-approves
  by default; proper Command(resume=...) UX waits for v6).
- **Cost computation** (per-provider pricing tables — belong upstream in
  the gateway registry).

## Rollback

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched
mv hive-swarm/swarm/llm/__init__.py.v4.bak           hive-swarm/swarm/llm/__init__.py
mv hive-swarm/swarm/llm/dispatch.py.v4.bak           hive-swarm/swarm/llm/dispatch.py
mv hive-swarm/swarm/nodes/worker.py.v4.bak           hive-swarm/swarm/nodes/worker.py
mv hive-swarm/swarm/nodes/queen.py.v4.bak            hive-swarm/swarm/nodes/queen.py
mv hive-swarm/swarm/models/agent.py.v4.bak           hive-swarm/swarm/models/agent.py
mv hive-swarm/swarm/models/config.py.v4.bak          hive-swarm/swarm/models/config.py
mv ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py.v4.bak \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py
rm hive-swarm/tests/test_v5_*.py
rm hive-swarm/smoke_test_tier3.py
rm ai-provider-swarm-gateway/tests/test_cli_swarm.py
```

## Acceptance checklist

- [ ] All file copies done (12 modified/new files)
- [ ] `pytest hive-swarm/tests/test_v5_*.py -q` → green
- [ ] `pytest hive-swarm/tests -q` → green (full regression)
- [ ] `pytest ai-provider-swarm-gateway/tests -q` → green (full regression)
- [ ] `python smoke_test.py` → identical to pre-v5 output
- [ ] `python hive-swarm/smoke_test_tier3.py` → workers fire, stub strings emitted
- [ ] `HIVE_SWARM_LLM_BACKEND=gateway python hive-swarm/smoke_test_tier3.py` → real LLM text + token totals
- [ ] `ai-provider-gateway swarm --help` works
- [ ] `ai-provider-gateway swarm --prompt "..."` runs end-to-end
- [ ] `ai-provider-gateway swarm --prompt "..." --backend gateway` returns real LLM output
