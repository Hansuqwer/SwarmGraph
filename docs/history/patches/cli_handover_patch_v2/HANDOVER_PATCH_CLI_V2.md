# Handover patch v2 — Lift `route` from stub

> Apply on top of v1. The upstream `models/state.py`, `graph/*`, `consensus/*`,
> `policy/*`, `providers/*` are now vendored on your box, so `route` becomes a
> real command. Adds `inspect-state` for schema diagnostics.

## What changed vs v1

| File | v1 | v2 |
|---|---|---|
| `cli.py` | `route` was a deferred stub (exit 2) | `route` invokes `build_gateway_graph()` end-to-end |
| `cli.py` | — | new `inspect-state` command for debugging schema drift |
| `cli.py::providers list` | basic list | adds `--capability` and `--free-only` filters |
| `cli.py::providers list` | required `name` | accepts `name` OR `provider_name` (upstream uses the latter) — already in your local fix; preserved |
| `tests/test_cli_route.py` | — | NEW — 8 route tests using the upstream `mock` adapter |

## Drop in

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# Replace just the CLI + add the new tests
cp cli_handover_patch_v2/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/cli.py
cp cli_handover_patch_v2/ai-provider-swarm-gateway/tests/test_cli_route.py \
   ai-provider-swarm-gateway/tests/test_cli_route.py

# No re-install needed (cli.py is already a known module after pip install -e)
```

## Verify

```bash
# 1) Schema-introspect the upstream GatewayState
.venv/bin/ai-provider-gateway inspect-state
# expected: a Rich table of fields incl. user_prompt, requested_capability,
#           preferred_provider_id, candidate_providers, audit_log, ...

# 2) Hint the mock provider, dry-run (no real API call)
.venv/bin/ai-provider-gateway route --prompt "explain CRDTs in 3 bullets" \
                                   --preferred mock --dry-run --show-audit

# 3) Same, JSON output
.venv/bin/ai-provider-gateway route --prompt "say hi" --preferred mock \
                                   --dry-run --json

# 4) Real call — uses whichever providers have credentials in your env
.venv/bin/ai-provider-gateway route --prompt "ping" --capability chat

# 5) New tests
.venv/bin/pytest ai-provider-swarm-gateway/tests/test_cli_route.py -q
# expected: ~8 passed (some may xskip if registry layout differs)
```

## How `route` works

1. **Imports** `GatewayState` + `build_gateway_graph` defensively. If anything
   is missing, exits 2 with the precise file list (same error path you saw in
   v1).
2. **Builds initial state** by intersecting `{user_prompt, requested_capability,
   preferred_provider_id, allow_unknown_quota, is_safe_to_proceed, audit_log,
   candidate_providers}` with `GatewayState.model_fields`. This is robust to
   upstream schema drift — if a field doesn't exist, it's silently dropped (the
   `extra='forbid'` model would have rejected it).
3. **Invokes** `build_gateway_graph().invoke(state.to_json_dict(),
   config={"configurable": {"thread_id": tid}})`. Falls back to no-config
   invocation if the graph signature differs.
4. **Reconstructs** the typed state from the result via
   `GatewayState.from_json_dict(...)` (or `model_validate(...)` if missing).
5. **Extracts** reportable fields by trying multiple plausible attribute names
   (`selected_provider_id` / `chosen_provider_id` / `winning_provider_id` /
   `routing_decision`; `response_text` / `final_response` / `response` /
   `validated_response`). This covers the three known upstream variants.
6. **Renders** with Rich panels by default; `--json` for machine output;
   `--show-audit` to dump every `audit_log` line.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Provider selected, response returned (or `--dry-run` succeeded) |
| 2 | Upstream gateway modules missing OR `GatewayState` could not be constructed |
| 3 | `graph.invoke()` raised |
| 4 | Graph completed but `is_safe_to_proceed=False` OR no provider selected (and not `--dry-run`) |

## Diagnosing schema drift

If `route` exits 4 with "no provider selected" or you see fields you don't
recognize in the JSON output, run:

```bash
.venv/bin/ai-provider-gateway inspect-state --json | jq .
```

Compare the printed fields against the `_extract_field` candidate-name lists
in `cli.py::route()`. If the upstream model exposes a new attribute (e.g.
`final_provider_id` instead of `selected_provider_id`), add it to the tuple
and re-run.

## Known cosmetic issue

LangGraph emits a `PendingDeprecationWarning: allowed_objects` from inside
its own checkpoint serde. Ignore it — it's resolved upstream in
`langgraph >= 0.4` and does not affect routing correctness.

## What's still deferred

| Item | Status |
|---|---|
| `ai-coder-hardening-improved` package | empty bundle — RR2/RR3 in fix_plan.md |
| Real LLM dispatch in `hive-swarm/swarm/nodes/worker.py` stubs | Production-deployment checklist item |
| `VectorMemoryAdapter` plugin (chromadb/hnswlib/faiss) | Production-deployment checklist item |

None of these block the gateway CLI.

## Appendix — the one-liner that proves it works

```bash
.venv/bin/ai-provider-gateway route --prompt "what is 2+2?" --preferred mock \
  --json | jq '{selected: .selected_provider, response: .response_text}'
```

Expected output (mock adapter):
```json
{
  "selected": "mock",
  "response": "MOCK RESPONSE: <the prompt echoed/templated>"
}
```
