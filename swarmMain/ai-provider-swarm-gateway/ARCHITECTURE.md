# ARCHITECTURE.md — AI Provider Swarm Gateway

## System Overview

```
User Prompt
    │
    ▼
GatewayState (Pydantic v2, extra='forbid', validate_assignment=True)
    │
    ▼
LangGraph Workflow (9 nodes)
  ┌────────────────────────────────────────────────────────┐
  │ 1. intake_node           — Validate, reject evasion    │
  │ 2. classify_request_node — Infer capability            │
  │ 3. provider_filter_node  — Capability + policy filter  │
  │ 4. quota_check_node      — Remove exhausted providers  │
  │ 5. swarm_route_node      — Score all candidates        │
  │ 6. consensus_node        — Cost-aware + policy-guarded │
  │ 7. provider_call_node    — Call selected adapter       │
  │ 8. response_validation_node — Validate response        │
  │ 9. usage_update_node     — Increment quota counters    │
  └────────────────────────────────────────────────────────┘
    │
    ▼
GatewayResponse (typed) + Audit Log (append-only)
```

## Module Structure

```
src/ai_provider_swarm_gateway/
├── models/
│   ├── provider.py    — ProviderInfo, ProviderQuota, AIModelInfo
│   ├── state.py       — GatewayState, GatewayResponse, RoutingDecision
│   ├── quota.py       — QuotaUsage, QuotaLimit, QuotaStatus
│   └── credentials.py — ProviderCredentialRef (env var names only)
├── registry/
│   ├── providers.yaml — Verified provider data (22 providers)
│   └── loader.py      — YAML → ProviderInfo validation
├── graph/
│   ├── builder.py     — build_gateway_graph() LangGraph factory
│   └── nodes.py       — All 9 node implementations
├── consensus/
│   └── strategies.py  — 4 consensus strategies (majority/weighted/policy/cost)
├── providers/
│   ├── base.py        — ProviderAdapter ABC
│   ├── mock_adapter.py — Always-configured test adapter
│   └── *_adapter.py   — One file per real provider
├── quota/
│   └── tracker.py     — JSON-backed local quota tracking
├── policy/
│   └── guardrails.py  — 3 guardrail functions
├── dashboard/
│   └── app.py         — Rich CLI table + Streamlit scaffold
└── cli.py             — Typer CLI entry point
```

## Key Design Decisions

### 1. Pydantic v2 for All State
- All state is a `GatewayState(BaseModel)` with `extra='forbid'`
- No raw dicts cross module boundaries
- `model_dump(mode='json')` / `model_validate()` for LangGraph serialization

### 2. LangGraph for Workflow
- Nodes are pure functions `dict -> dict`
- Conditional edges handle no-candidates and no-provider-selected cases
- `InMemorySaver` checkpointer for replay and debugging
- `_MockGraph` fallback when LangGraph not installed

### 3. Policy Guardrails at Every Boundary
- `intake_node`: checks for prohibited request metadata
- `provider_filter_node`: checks credentials, web-only, confidence
- `consensus_node`: `policy_guarded_consensus` rejects policy-blocked providers
- `quota_check_node`: removes exhausted providers before routing

### 4. Swarm Consensus
- `swarm_route_node`: scores all candidates (parallel evaluation)
- `consensus_node`: applies `cost_aware_consensus` → prefers verified free providers
- Policy guard applied inside every consensus strategy function

### 5. Local-First Quota Tracking
- JSON file at `~/.ai_provider_gateway/usage.json`
- Append-only increments (no hidden decrements)
- Reset only when `reset_at` timestamp passes
- Unknown limits treated conservatively
