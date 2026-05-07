# PROJECT_REVIEW.md — AI Provider Swarm Gateway
## Complete Step-by-Step Review for Human & AI Reviewers

---

## 1. Executive Summary

This project is a **safe, compliant, auditable AI provider routing gateway** built with Pydantic v2, LangGraph, and swarm-style consensus routing. It helps users discover AI providers with legitimate free/trial API access and route requests across their own configured provider credentials. It does **not** enable quota evasion, account rotation, CAPTCHA bypass, or any unauthorized automation.

---

## 2. What This Project Does

- Maintains a typed, versioned YAML registry of AI providers with verified free-tier data
- Validates all provider data using Pydantic v2 models with `extra='forbid'`
- Routes user requests through a LangGraph workflow: intake → classify → filter → quota check → swarm route → consensus → call → validate → log
- Enforces policy guardrails that block unsafe routing patterns
- Tracks per-provider usage locally (JSON file or SQLite)
- Provides a Rich CLI dashboard and optional Streamlit UI
- Runs fully offline using mock adapters — no credentials required for testing

---

## 3. What This Project Does NOT Do

| Prohibited Behavior | Status |
|---|---|
| Automatic account creation | ❌ Blocked by policy guardrails |
| Account rotation / farming | ❌ Blocked by policy guardrails |
| CAPTCHA bypass | ❌ Not implemented, blocked by policy |
| Fake identity generation | ❌ Not implemented |
| Scraping private web sessions | ❌ Not implemented |
| Rotating multiple accounts to bypass free-tier | ❌ Blocked — single credential per provider |
| Circumventing rate limits | ❌ Quota tracker enforces limits |
| Treating "web-only free" as "API free" | ❌ Flagged in registry, blocked in routing |
| Using unknown limits as if free | ❌ `unknown` confidence → not routed as free |
| Hiding or resetting usage counters | ❌ Counters are append-only audit log |

---

## 4. Compliance Boundary

**Allowed:**
- User configures their own API keys via environment variables
- Gateway routes across credentials the user legitimately owns
- Quota-aware routing respects each provider's stated limits
- Graceful fallback when quota is exhausted
- Clear warnings when a provider only has web-free access (not API-free)

**Not Allowed:**
- Any form of automatic credential generation
- Any form of account switching to bypass per-account free limits
- Any automation of provider sign-up flows

---

## 5. Critical Feasibility Review

### What Works
- **Groq, Google Gemini, Mistral, Cerebras, Cohere, Cloudflare Workers AI**: Have verified permanent free API tiers. Fully feasible to integrate via standard API keys.
- **OpenRouter**: Has free models (community-sourced). Feasible via API key.
- **DeepSeek**: Has initial token credit + very low cost. Feasible.
- **Mock provider**: Fully works out-of-box with no credentials.
- **LangGraph workflow**: Compiles and runs synchronously with dict-based state.
- **Pydantic v2 models**: Fully typed, hardened, and round-trip safe.
- **CLI dashboard**: Works immediately from the provider YAML.

### What Is Risky
- **Rate limit data may change**: All provider rate limits are verified as of May 2026 but change frequently. Confidence labels are included.
- **Provider API compatibility**: Most providers use OpenAI-compatible APIs. Some (Cohere, Google) have different SDKs.
- **Zhipu GLM**: Free tier limits are undocumented. Marked `unknown`.
- **Moonshot Kimi**: API pricing and free tier unknown for international users.
- **DeepSeek**: 5M token credit is a one-time grant, not a recurring free tier.

### What Must Be Mocked
- All actual LLM calls in tests use `mock_adapter.py`
- Real adapter stubs return `NotConfiguredResponse` when credentials are absent
- No credentials needed for `pytest` to pass

### What Should Be Deferred
- OAuth flows (complex, provider-specific)
- NVIDIA NIM integration (trial credit system, non-trivial auth)
- Full Streamlit dashboard (scaffolded, not wired)
- Replicate, Perplexity, xAI full adapters (stub only)

---

## 6. Provider Research Methodology

Research was conducted via:
- [apiscout.dev/guides/free-ai-apis-developers-2026](https://apiscout.dev/guides/free-ai-apis-developers-2026) (March 2026)
- [awesomeagents.ai/tools/free-ai-inference-providers-2026](https://awesomeagents.ai/tools/free-ai-inference-providers-2026) (April 2026)
- [softtechhub.us/2026/04/05/list-of-free-ai-apis](https://softtechhub.us/2026/04/05/list-of-free-ai-apis/) (April 2026)
- [dev.to/bd_perez/save-money-on-ai-using-those-permanent-free-llm-apis-19ec](https://dev.to/bd_perez/save-money-on-ai-using-those-permanent-free-llm-apis-19ec) (March 2026)
- [belski.me/blog/ai_inference_providers_2026_free_tier_deep_dive](https://belski.me/blog/ai_inference_providers_2026_free_tier_deep_dive/) (April 2026)
- [github.com/cheahjs/free-llm-api-resources](https://github.com/cheahjs/free-llm-api-resources) (May 2026)
- Alibaba Cloud Model Studio documentation (March 2026)

**Rules applied:**
- `unknown` used when data could not be confirmed from two sources
- Free web usage distinguished from free API usage
- Trial credit distinguished from recurring free usage
- All data timestamped with `last_verified: "2026-05-07"`

---

## 7. Provider Registry Schema

See `src/ai_provider_swarm_gateway/registry/providers.yaml` and `PROVIDER_REGISTRY.md`.

Key fields: `provider_id`, `free_daily_usage`, `free_monthly_usage`, `trial_credits`, `api_access_available`, `web_only_free_access`, `requires_payment_method`, `confidence`, `source_links`, `last_verified`.

---

## 8. Gateway Architecture

```
User Request
    │
    ▼
GatewayState (Pydantic v2)
    │
    ▼
LangGraph Workflow
  ┌─────────────────────────────────────────────────┐
  │ intake_node → classify_request_node             │
  │     → provider_filter_node                      │
  │     → quota_check_node                          │
  │     → swarm_route_node (parallel evaluation)    │
  │     → consensus_node (policy-guarded)           │
  │     → provider_call_node                        │
  │     → response_validation_node                  │
  │     → usage_update_node → END                   │
  └─────────────────────────────────────────────────┘
    │
    ▼
GatewayResponse (typed) + Audit Log
```

---

## 9. LangGraph Flow

Each node is a pure function `(dict) -> dict`. The compiled graph uses `InMemorySaver` for checkpointing. All state is `GatewayState`-typed via `model_validate` / `to_json_dict`.

Conditional edges:
- After `quota_check_node`: if no providers remain → END with error
- After `consensus_node`: if no provider selected → END with error
- After `response_validation_node`: if validation fails → fallback or END

---

## 10. Pydantic Model Review

All models use `ConfigDict(extra='forbid')`. Key models:
- `ProviderInfo`: Provider metadata, immutable registry entry
- `ProviderQuota`: Free tier data with `confidence` field
- `GatewayState`: Mutable workflow state, bounded lists
- `QuotaUsage`: Append-only usage counter with non-negative validator
- `ProviderCredentialRef`: Validates env var name (not raw secret)
- `RoutingDecision`: Typed routing output with policy warnings
- `GatewayResponse`: Typed provider response with error field

---

## 11. Quota Tracking Design

- Storage: `~/.ai_provider_gateway/usage.json` (JSON file, SQLite optional)
- Increment: per request, per provider
- Reset: if `reset_at` is set and passed, counters reset
- Conservative: `unknown` quota → treated as not free unless user opts in
- Audit: all usage changes logged to `audit_log` in state

---

## 12. Auth Design

- All credentials via environment variables only
- `.env.example` provided, never committed secrets
- `ProviderCredentialRef.credential_env_var` validated to be a var name, not a raw key
- `SecretBackend` supports `env`, `dotenv`, `vault` (stub)
- No credential storage in YAML, JSON, or code

---

## 13. Dashboard Design

- **CLI**: `typer` + `rich` table showing all providers with links and quota info
- **Streamlit**: Scaffolded app (requires `pip install streamlit`)
- Both load from `providers.yaml` registry
- All links are official provider URLs

---

## 14. Testing Plan

5 test modules:
1. `test_models.py` — Pydantic model validation, field constraints, round-trip
2. `test_registry.py` — YAML loading, schema validation, provider count
3. `test_quota.py` — Usage tracking, exhaustion, unknown conservative behavior
4. `test_routing.py` — Filter logic, preference ordering, credential checks
5. `test_policy.py` — Guardrail blocking, web-only as API blocking, account rotation blocking
6. `test_graph.py` — LangGraph workflow with mock provider
7. `test_provider_adapters.py` — Mock adapter, stub adapter behavior
8. `test_e2e.py` — Full mock gateway request end-to-end

All tests pass with mock data, no credentials required.

---

## 15. Known Risks

1. Provider rate limits change frequently — use `last_verified` to flag stale data
2. Some providers (Zhipu, Kimi) have undocumented or region-restricted free tiers
3. OpenRouter free model availability depends on upstream providers
4. DeepSeek 5M token credit is one-time, not recurring
5. Together AI no longer has a free tier — requires $5 minimum deposit

---

## 16. Known Unknowns

- Exact Moonshot Kimi international API availability
- Zhipu GLM precise rate limits
- Whether Perplexity has a permanent free API tier
- Whether NVIDIA NIM credits have changed since April 2026

---

## 17. What Must Be Verified Manually

Before production use, manually verify:
- [ ] Your target provider's current free tier limits at their official docs page
- [ ] Whether your account region qualifies for free quota (Qwen/Alibaba: Singapore only)
- [ ] Whether your provider plan includes API access (not just web access)
- [ ] Current rate limits (check provider status page)

---

## 18. Future Improvements

- Async LangGraph nodes for parallel provider calls
- Real HNSW/vector memory for routing pattern learning
- OAuth flow support for providers that support it
- SQLite-backed quota persistence with WAL mode
- Prometheus/OpenTelemetry metrics export
- Provider health monitoring background worker
- Streaming response support

---

## 19. Step-by-Step AI Reviewer Guide

To review this project as an AI:

### Step 1: Read mission and compliance
- Read `MISSION_LOCK.md` — verify mission is preserved
- Read `COMPLIANCE.md` — verify all prohibited behaviors are listed and blocked
- Read `PROJECT_REVIEW.md` Section 3 — verify prohibited behaviors table is complete

### Step 2: Review provider data
- Open `src/ai_provider_swarm_gateway/registry/providers.yaml`
- For each provider: check `confidence` field, check `api_access_available`, check `web_only_free_access`
- Verify no provider with `confidence: unknown` has `free_daily_usage` set to a specific number
- Verify all `source_links` are non-empty for `confidence: verified` providers

### Step 3: Review Pydantic models
- Open `src/ai_provider_swarm_gateway/models/provider.py` — verify `ConfigDict(extra='forbid')`
- Open `src/ai_provider_swarm_gateway/models/state.py` — verify `GatewayState` is hardened
- Open `src/ai_provider_swarm_gateway/models/credentials.py` — verify no raw secrets stored
- Open `src/ai_provider_swarm_gateway/models/quota.py` — verify non-negative validator

### Step 4: Review policy guardrails
- Open `src/ai_provider_swarm_gateway/policy/guardrails.py`
- Verify `can_route_to_provider` blocks: no-credential, web-only-as-API, unknown-as-free
- Verify `reject_quota_evasion` blocks: account rotation flag
- Verify `validate_provider_policy` returns warnings for policy violations

### Step 5: Review LangGraph graph
- Open `src/ai_provider_swarm_gateway/graph/builder.py`
- Verify graph compiles with `build_gateway_graph()`
- Verify all 9 nodes are present
- Verify conditional edges handle empty provider lists

### Step 6: Review provider adapters
- Open `src/ai_provider_swarm_gateway/providers/base.py` — verify abstract interface
- Open `src/ai_provider_swarm_gateway/providers/mock_adapter.py` — verify deterministic test response
- Open any real adapter stub — verify it checks env var before calling API
- Verify no hardcoded secrets in any adapter file

### Step 7: Review quota tracker
- Open `src/ai_provider_swarm_gateway/quota/tracker.py`
- Verify `increment()` never decrements
- Verify `is_exhausted()` returns True conservatively for unknown limits
- Verify `reset_if_due()` only resets when `reset_at` has passed

### Step 8: Review tests
- Open `tests/test_policy.py` — verify account rotation is blocked
- Open `tests/test_routing.py` — verify unconfigured providers are rejected
- Open `tests/test_e2e.py` — verify full graph runs with mock provider

### Step 9: Run tests
```bash
cd ai-provider-swarm-gateway
pip install -e ".[test]"
pytest tests/ -v
```
All tests must pass without any API credentials.

### Step 10: Run CLI dashboard
```bash
ai-provider-gateway dashboard
```
Dashboard must display all providers with correct free-tier data.

---

## 20. File-by-File Review Checklist

| File | What to check |
|---|---|
| `MISSION_LOCK.md` | Mission hash preserved |
| `COMPLIANCE.md` | Prohibited behaviors listed |
| `providers.yaml` | confidence labels, source_links, no invented limits |
| `models/provider.py` | extra='forbid', field validators |
| `models/state.py` | GatewayState hardened, bounded lists |
| `models/credentials.py` | No raw secrets, env var name validation |
| `models/quota.py` | Non-negative validator, conservative unknown handling |
| `policy/guardrails.py` | All 3 guardrail functions present |
| `graph/builder.py` | 9 nodes, conditional edges, compiles |
| `graph/nodes.py` | Each node is pure, no side effects outside state |
| `providers/base.py` | Abstract interface, `is_configured()` checks env |
| `providers/mock_adapter.py` | Deterministic, simulates quota and failure |
| `quota/tracker.py` | Load/save/increment/reset logic |
| `consensus/strategies.py` | All 4 strategies, policy guard applied |
| `dashboard/app.py` | Loads from YAML, no hardcoded data |
| `cli.py` | No credentials in CLI args |
| `tests/test_policy.py` | Account rotation blocked, web-only blocked |
| `tests/test_e2e.py` | Runs without credentials |
| `.env.example` | Only var names, no values |
| `pyproject.toml` | Correct dependencies |
