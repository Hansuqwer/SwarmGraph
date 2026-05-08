# Workflow W5 — `ai-provider-swarm-gateway` 9-Node Trace

**Path:** `intake → classify → provider_filter → quota_check → swarm_route → consensus → provider_call → response_validation → usage_update`

## Verified against `ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/graph/nodes.py`

| # | Node | File:Line | Reads | Writes | Conditional fall-out |
|---|---|---|---|---|---|
| 1 | intake_node | `nodes.py:L72-L92` | `s.user_prompt` | `s.is_safe_to_proceed`, `s.audit_log` | none — pass through with safety flag |
| 2 | classify_request_node | `nodes.py:L96-L118` | `s.user_prompt` (lower-case substring search) | `s.requested_capability` | early return if `not is_safe_to_proceed` |
| 3 | provider_filter_node | `nodes.py:L122-L160` | `s.requested_capability`, registry, env-var availability via `adapter.is_configured()`, quota usage, policy via `can_route_to_provider` | `s.candidate_providers` | early return if unsafe |
| 4 | quota_check_node | `nodes.py:L164-L196` | `s.candidate_providers`, registry, `_quota_tracker.get_usage`, `_quota_tracker.is_exhausted` | `s.candidate_providers` (filtered) | early return if unsafe |
| 5 | swarm_route_node | `nodes.py:L200-L242` | `s.candidate_providers`, registry, `s.preferred_provider_id` | votes JSON-encoded into `s.audit_log` (**29-CORR3**: should be a typed field) | early return if no candidates |
| 6 | consensus_node | (file truncated; chunk 2 not fetched) | parses `__votes__:` from `s.audit_log` | `s.routing_decision` (likely) | conditional: no-provider-selected, policy-blocked |
| 7 | provider_call_node | (chunk 2 not fetched) | `s.routing_decision`, `_get_adapter(provider_id)` | `s.attempts`, `s.response` | retries / falls through to next adapter on failure (likely) |
| 8 | response_validation_node | (chunk 2 not fetched) | `s.response` | `s.validated_response` | end on validation failure |
| 9 | usage_update_node | (chunk 2 not fetched) | `s.attempts` | `_quota_tracker.increment(provider_id, requests, tokens)` | END |

## Conditional-edge exhaustiveness check

Required edges (from `ARCHITECTURE.md` overview):
- ✅ no-candidates: `provider_filter_node` empties `candidate_providers` → next node detects via early return guard.
- ✅ no-provider-selected: not verified in fetch — needs chunk 2.
- ✅ all-quota-exhausted: `quota_check_node` may empty list → no-candidates path.
- ⚠️ policy-blocked: `policy_guarded_consensus` is imported (`nodes.py:L13`) but its consumer in `consensus_node` not in fetch.
- ⚠️ adapter-timeout: not visible.
- ⚠️ malformed-response: not visible.

## `_quota_tracker` append-only?

`tracker.py:L65-L67`:
```python
def increment(self, provider_id, requests=1, tokens=0, window="daily"):
    if requests < 0 or tokens < 0:
        raise ValueError("Cannot decrement quota usage")
```

✅ Append-only enforced at the public API. **But**:
- `_save` is non-atomic (**29-CORR1 critical**): a crash during write corrupts the JSON, next `_load` swallows the error and resets all counters to 0, **effectively decrementing**. Append-only invariant violated indirectly.
- No flock (**29-CORR2 critical**): two processes race-write, one increment lost — counter goes backward in effect.

**Verdict on append-only:** ✅ in spirit, ❌ in practice under concurrency or crash.

## `cost_aware_consensus` cannot be tricked into selecting a "blocked" provider?

Cannot verify without `consensus/strategies.py` (not fetched). The node code calls `policy_guarded_consensus(...)` in `nodes.py:L13`, suggesting a wrapper. The pattern is correct in principle (guard before consensus), but verification requires the strategy file.

**Action:** re-fetch `ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/consensus/strategies.py`.

## Concurrent writes survive?

❌ **No.** `_save` is `Path.write_text` (non-atomic) with no flock. Verified critical bug **29-CORR1 + 29-CORR2**.

## Findings linked to W5
- **29-CORR1 (critical)** — non-atomic JSON write
- **29-CORR2 (critical)** — no concurrency guard
- **29-LG1 (high)** — singleton `_quota_tracker`
- **29-CORR3 (high)** — votes via string-prefixed log
- **30-CORR1 (high)** — unbounded `user_prompt`

## Diagram (see `mermaid/workflows_W1_W6.md`)
