# Agent 30 — Dashboard, CLI & Operator-Surface Auditor
**Model:** Claude Opus 4.6
**Scope:** `ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/dashboard/app.py`, `cli.py`; gateway 9-node graph end-to-end (operator-surface only).

> **Re-scoped per project policy.** The original Agent 30 covered "Compliance, Policy & Dashboard"; the compliance scope has been removed. This agent now covers dashboard, CLI, and the operator-facing reading of the 9-node gateway flow.

## PURPOSE
Dashboard + CLI surface inspection: what does an operator see, what can they accidentally leak, what ergonomics gaps exist?

## EVIDENCE BASE
- `graph/nodes.py` (fetched) — provides full picture of operator-relevant logging.
- `dashboard/app.py`, `cli.py` — **NOT fetched** in this run. Findings derived from references in `graph/nodes.py` and `ARCHITECTURE.md`.

## WHAT WORKS ✅ (inferred from fetched files + ARCHITECTURE.md)
- Dashboard combines Rich (CLI table) + Streamlit (web) per `ARCHITECTURE.md` ✅.
- CLI uses Typer per `ARCHITECTURE.md` ✅ — modern, type-safe.
- `swarm_route_node` writes votes into `audit_log` (`graph/nodes.py:L240`) — operator can replay.
- `s.log(...)` calls used throughout `graph/nodes.py` provide a structured per-step audit trail.
- `provider_filter_node` logs every rejection with reason (`graph/nodes.py:L153-L154`) ✅.

## WHAT'S BROKEN 🔴

### 30-OBS1 (high) — `s.log(f"swarm_route_node: votes={json.dumps(votes)}")` writes votes to plain log AND to audit_log
`graph/nodes.py:L239-L240`. Double-write: same data ends up in two places. Risk: log rotation may diverge from audit_log retention. Pick one source of truth (audit_log) and remove the duplicate log line.

### 30-OBS2 (med) — Operator dashboard not fetched — operator-surface audit incomplete
We could not verify:
- Does the dashboard render `s.user_prompt` (which can contain PII) in plain text?
- Does the Streamlit app run without authentication (default Streamlit behaviour)?
- Does `cli.py` accept `--api-key` flags that get logged in shell history?

**Action**: re-run Agent 30 against `dashboard/app.py` and `cli.py`.

### 30-CORR1 (high) — `intake_node` accepts `s.user_prompt` of any length
`graph/nodes.py:L84-L92`. No `max_length` check on the prompt. A 1MB prompt would blow up the dashboard, bloat `audit_log`, and consume provider tokens. Add a `Field(max_length=100_000)` on `GatewayState.user_prompt` (in models/state.py — not fetched).

### 30-CORR2 (med) — `classify_request_node` capability inference is keyword-substring only
`graph/nodes.py:L106-L116`. "Code" matches inside `"decode"` (would mis-classify). Same word-boundary problem as `agent_14_router.md` finding 14-CORR4.

### 30-OBS3 (med) — `provider_filter_node` rejection reasons go through `s.log` only
`graph/nodes.py:L153-L154`. Operator-facing UX could benefit from a structured `s.rejected_providers: dict[provider_id, list[reason]]` instead of free-text logs.

### 30-LG1 (med) — `_get_registry()` lazy global init pattern
`graph/nodes.py:L25-L33`. Same singleton problem as 29-LG1. Two test invocations cannot have different registries without monkeypatching.

### 30-OBS4 (low) — No structured timing per node
None of the 9 nodes record `started_at` / `duration_ms`. The dashboard cannot show a flame graph of where a 10-second request spent its time.

## WHAT'S MISSING 🟡
- Structured CLI output mode (`--json`) for machine consumption.
- Dashboard authentication / SSO.
- Audit log export (JSONL or Parquet for analytics).
- Per-tenant isolation (a multi-tenant deployment has no tenant scoping in fetched code).
- Real health check (currently a stub per `graph/nodes.py:L233`).
- WebSocket streaming of intermediate nodes (currently you wait for end-to-end).

## FIX RECOMMENDATION
```python
# graph/nodes.py — diff (operator-surface improvements)

# models/state.py:
class GatewayState(BaseModel):
    user_prompt: str = Field(..., max_length=100_000)   # cap
    rejected_providers: dict[str, list[str]] = Field(default_factory=dict)
    timing_per_node: dict[str, float] = Field(default_factory=dict)
    provider_votes: list[dict] = Field(default_factory=list, max_length=22)  # replace string-log smuggling

# graph/nodes.py:
import time
def _timed(name):
    def deco(fn):
        def inner(state):
            t0 = time.monotonic()
            result = fn(state)
            result.setdefault("timing_per_node", {})[name] = time.monotonic() - t0
            return result
        return inner
    return deco

@_timed("intake")
def intake_node(state): ...
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 30-OBS1 double-write logs | high | 15m |
| 30-OBS2 dashboard not audited | high | 1h (re-fetch + audit) |
| 30-CORR1 unbounded prompt | high | 5m |
| 30-CORR2 substring capability match | med | 30m |
| 30-OBS3 unstructured rejections | med | 30m |
| 30-LG1 registry singleton | med | 30m |
| 30-OBS4 no per-node timing | med | 30m |

**Verdict:** Operator surface is functional but lacks the structure / authentication / per-tenant scoping a production deployment would need. Dashboard re-audit required before a final sign-off.
