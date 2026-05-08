# Handover patch v3 — wire `route --preferred 9router`

Adds 9router as an OpenAI-compatible adapter. **Does not** rewrite `cli.py`,
`quota/tracker.py`, or anything else you've already patched locally.

## Files in this patch

```
cli_handover_patch_v3/ai-provider-swarm-gateway/
├── src/ai_provider_swarm_gateway/providers/
│   └── nine_router_adapter.py                          ← NEW (drop-in)
├── registry/
│   └── 9router_entry.yaml                              ← snippet to APPEND
├── tests/
│   ├── test_nine_router_adapter.py                     ← NEW (~30 tests, mocked HTTP)
│   └── test_nine_router_route_integration.py           ← NEW (CLI → graph → adapter)
└── PATCH_graph_nodes_get_adapter.md                    ← 2-line edit recipe
```

## Apply (4 steps, ~2 minutes)

```bash
cd /Users/hansvilund/HansuQWER/pydlangswarm/pylangSWARM/swarmMain_patched

# 1) Drop in the adapter
cp cli_handover_patch_v3/ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py \
   ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py

# 2) Drop in the tests
cp cli_handover_patch_v3/ai-provider-swarm-gateway/tests/test_nine_router_adapter.py \
   ai-provider-swarm-gateway/tests/test_nine_router_adapter.py
cp cli_handover_patch_v3/ai-provider-swarm-gateway/tests/test_nine_router_route_integration.py \
   ai-provider-swarm-gateway/tests/test_nine_router_route_integration.py

# 3) Append the registry entry — open both files in your editor and paste the
#    snippet from cli_handover_patch_v3/.../registry/9router_entry.yaml into the
#    `providers:` list inside ai-provider-swarm-gateway/src/.../registry/providers.yaml.
#    (One block, indentation already correct.)

# 4) Edit graph/nodes.py per PATCH_graph_nodes_get_adapter.md (2 lines: an import + a dict entry)
```

## Run (no live endpoint needed)

```bash
source .venv/bin/activate

# Adapter unit tests (no network)
pytest ai-provider-swarm-gateway/tests/test_nine_router_adapter.py -q
# expected: ~30 passed

# CLI integration tests (mocked adapter)
pytest ai-provider-swarm-gateway/tests/test_nine_router_route_integration.py -q
# expected: 5 passed (some skip if registry not appended)

# Regression: existing suites still green
pytest ai-provider-swarm-gateway/tests/test_cli.py -q
pytest ai-provider-swarm-gateway/tests/test_cli_route.py -q
pytest ai-provider-swarm-gateway/tests/test_quota_atomic.py -q

# Verify the registration landed
.venv/bin/ai-provider-gateway providers list | grep 9router
.venv/bin/python -c "
from ai_provider_swarm_gateway.graph.nodes import _get_adapter
a = _get_adapter('9router')
print(type(a).__name__, '— configured:', a.is_configured(), '— model:', a.model)
"
```

## Run against live 9router

```bash
export AI_PROVIDER_GATEWAY_9ROUTER_BASE_URL=http://localhost:20128/v1
export AI_PROVIDER_GATEWAY_9ROUTER_MODEL=kc/kilo-auto/free
export AI_PROVIDER_GATEWAY_9ROUTER_API_KEY=<your-key>

.venv/bin/ai-provider-gateway route \
  --prompt "Say only pong." \
  --preferred 9router \
  --capability chat \
  --json
```

Expected (compact JSON, single line per your CLI's setting):
```json
{"selected_provider": "9router", "response_text": "pong", ...}
```

If the upstream `routing_decision` doesn't surface `selected_provider_id`
under one of the names the CLI checks, you'll see `selected_provider: null`
but `response_text: "pong"` should still be set (the adapter ran). In that
case, run `ai-provider-gateway inspect-state --json | jq` and add the actual
attribute name to the `_extract_field` tuple in `cli.py` (you already did
this for `routing_decision.selected_provider_id` and `provider_response.content`
per your handover note — same pattern if anything new shows up).

## Design notes (what you're getting)

| Concern | Decision |
|---|---|
| HTTP client | stdlib `urllib.request` — zero new deps |
| Response quirk (`data: [DONE]` trailer) | `_parse_quirky_body` splits on `\ndata:` first (preserves `data:` substrings inside content), falls back to first `data:` |
| Content extraction | three-level fallback: `message.content` → `message.reasoning` → `choices[0].text` |
| Auth | `AI_PROVIDER_GATEWAY_9ROUTER_API_KEY` primary; `ROUTER_API_KEY`, `NINEROUTER_API_KEY`, `KILO_CODE_API_KEY`, `OPENAI_API_KEY` aliases |
| ABC compatibility | imports `providers.base.ProviderAdapter` if present; falls back to a duck-typed base if not. Implements `chat`, `chat_completion`, `complete`, `call`, `invoke` (every method name the upstream graph might dispatch to) |
| Test isolation | adapter constructor accepts an injected `http_client`; tests use `FakeHttpClient` — zero localhost dependency |
| Config injection | constructor accepts `base_url`, `model`, `api_key`, `timeout_seconds` overrides; env vars are the default source |
| Capabilities | `supports("chat")` and `supports("code")` return True; embeddings/image return False (matches kilo-auto reality) |

## Compact JSON from CLI

You noted route JSON is now compact single-line. The integration test
parses `out[out.find("{"):]` so it works whether the JSON is single-line or
indented — no breakage.

## What if `_get_adapter` lives somewhere else in your tree

Some upstream versions put the adapter dispatch in `graph/builder.py` or
factor it into a `providers/__init__.py` registry. Find it with:

```bash
grep -rn "MockAdapter()" ai-provider-swarm-gateway/src/
```

Then add the same two lines (import + dict entry) at that site.

## Rollback

```bash
rm ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/providers/nine_router_adapter.py
rm ai-provider-swarm-gateway/tests/test_nine_router_adapter.py
rm ai-provider-swarm-gateway/tests/test_nine_router_route_integration.py
# revert your registry/providers.yaml + graph/nodes.py edits with git
```

No other files were touched.

## Acceptance checklist

- [ ] `nine_router_adapter.py` copied
- [ ] Two test files copied
- [ ] `registry/providers.yaml` has a 9router entry
- [ ] `graph/nodes.py:_get_adapter` has the import + dict entry
- [ ] `pytest ai-provider-swarm-gateway/tests/test_nine_router_adapter.py -q` → green
- [ ] `pytest ai-provider-swarm-gateway/tests/test_nine_router_route_integration.py -q` → green (or skip due to registry)
- [ ] `pytest ai-provider-swarm-gateway/tests/test_cli{,_route}.py -q` → still green (regression)
- [ ] `pytest ai-provider-swarm-gateway/tests/test_quota_atomic.py -q` → still green (regression)
- [ ] With env vars set: `ai-provider-gateway route --preferred 9router --prompt "Say only pong." --json` returns `pong`
