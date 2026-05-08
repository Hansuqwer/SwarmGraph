# Agent 18 — Judge / Anti-Drift Node Auditor
**Model:** Claude Opus 4.6
**Scope:** `hive-swarm/swarm/nodes/judge.py`

## PURPOSE
Drift detection via `objective_hash`, false-positive analysis, escalation path.

## PUBLIC SURFACE (verified)
- `judge_node(state) -> dict`
- `route_after_judge(state) -> str` — `{distill_node, route_task, end}`

## WHAT WORKS ✅
- `swarm.status = "judging"` set before any branching (`judge.py:L20`) — clean state machine.
- Empty `candidate` triggers `swarm.fail("all_workers_failed", ...)` (`judge.py:L26-L31`) ✅.
- `check_drift()` is correctly conditional on `config.anti_drift_enabled` ✅.
- Drift detection sets `failure_cause = "objective_drift"` ✅ matching the typed FailureCause literal.
- `final_output = candidate` set only when accepted (`judge.py:L51`) ✅.
- Status transitions to `"distilling"` to trigger SONA next (`judge.py:L52`) ✅.
- Retry edge: `route_after_judge` returns `route_task` when iter < max (`judge.py:L66`) ✅.

## WHAT'S BROKEN 🔴

### 18-CORR1 (high) — Drift detection is keyword-overlap; suffers high false-positive rate
`models/state.py:L143-L155` (the implementation `check_drift` calls):
```python
obj_tokens = set(self.objective.lower().split())
out_tokens = set(candidate_output.lower().split())
overlap = len(obj_tokens & out_tokens) / len(obj_tokens)
return overlap >= self.config.anti_drift_similarity_threshold  # default 0.4
```
For objective "Implement OAuth2 authentication with refresh tokens":
- `obj_tokens = {"implement", "oauth2", "authentication", "with", "refresh", "tokens"}`
- A perfectly correct output that says "I built JWT auth using bearer tokens, supporting renewal" → tokens `{"i", "built", "jwt", "auth", "using", "bearer", "tokens", "supporting", "renewal"}` → overlap with obj = `{"tokens"}` = 1/6 = 0.17 < 0.4 → **incorrectly flagged as drift**.

For objective "fix typo":
- A 5000-word LLM hallucination including the words "fix" and "typo" passes drift check → **false negative**.

The default 0.4 threshold is arbitrary. Recommend embedding-cosine similarity once vector adapter is real. Until then, document the limitation in the docstring.

### 18-CORR2 (med) — `judge_node` does NOT use `swarm.assert_no_drift()`
`judge.py:L41-L48` calls `swarm.check_drift(candidate)` and manually does the failure transition. The `state.py:L157-L165` defines `assert_no_drift()` which does the same thing but in one call. Inconsistent — pick one.

### 18-LG1 (high) — `route_after_judge` returns `"route_task"` to retry, but `route_task` doesn't reset `pending_votes`, `worker_results`, or `consensus_result`
On retry:
- `pending_votes = []` (cleared by `consensus_node` ✅)
- `worker_results` carries over from previous attempt (NOT cleared) — next consensus sees stale results
- `consensus_result` carries over (NOT cleared)
- `agents` list carries over (likely intended)

So the retry is **not a clean retry**. Recommend: clear `worker_results = []` and `consensus_result = None` before re-routing.

### 18-CORR3 (med) — `judge.py:L34-L36` reads `consensus_result.action` but the consensus_result was set by the previous `consensus_node` call
If `judge_node` is reached without a `consensus_result` (e.g., directly from a tier-1/tier-2 path), it falls back to `latest_output or ""`. **But** `fast_agent_node` and `medium_agent_node` set `final_output` and route directly to `distill_node`, **skipping judge entirely**. So this fallback is dead code. Either delete the fallback or wire the tier-1/2 paths through judge.

### 18-OBS1 (low) — On accepted output, history entry says `output_hash: latest_output_hash`, but at this point `latest_output` may be the same as `final_output` we just set
`judge.py:L55-L59`. If `consensus_result` was set, `latest_output_hash` was updated by `record_worker_result`. Otherwise it's empty. Defensive: log the actual hashed value (`stable_hash(candidate)[:8]`).

## WHAT'S MISSING 🟡
- No "soft drift" threshold (e.g., warn at 0.3, fail at 0.4).
- No "drift trend" tracking (was the last 3 outputs drifting more each time?).
- No drift-explanation: which tokens are missing.
- `judge_node` should optionally call `memory_retrieve` to find similar past objectives that succeeded — closing the SONA loop properly.

## FIX RECOMMENDATION
```python
# judge.py — diff
def judge_node(state):
    swarm = SwarmState.model_validate(state)
    swarm.status = "judging"
    candidate = swarm.latest_output or (swarm.consensus_result.action if swarm.consensus_result else "")
    if not candidate.strip():
        swarm.fail("all_workers_failed", "Judge received empty output from consensus")
        swarm.append_history("judge", {"outcome": "empty_output"})
        return swarm.to_json_dict()

    try:
        swarm.assert_no_drift(candidate)   # consolidate to one method
    except ValueError as exc:
        swarm.append_history("drift_detected", {
            "objective_hash": swarm.objective_hash,
            "candidate_preview": candidate[:100],
            "missing_tokens": list(set(swarm.objective.lower().split()) - set(candidate.lower().split()))[:10],
        })
        return swarm.to_json_dict()

    swarm.final_output = candidate
    swarm.status = "distilling"
    swarm.append_history("judge", {"outcome": "accepted", "output_hash": stable_hash(candidate)[:8]})
    return swarm.to_json_dict()

def route_after_judge(state):
    swarm = SwarmState.model_validate(state)
    if swarm.status == "failed":
        if swarm.iteration < swarm.config.max_iterations:
            # CLEAN RETRY: clear ephemeral state
            swarm.worker_results = []
            swarm.consensus_result = None
            swarm.status = "routing"
            return "route_task"
        return "end"
    return "distill_node"
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 18-CORR1 keyword drift | high | 1wk (real embeddings) / 1d (AST) |
| 18-CORR2 inconsistent assertion | med | 5m |
| 18-LG1 dirty retry | high | 30m |
| 18-CORR3 dead fallback | med | 15m |
| 18-OBS1 hash logging | low | 5m |
