# Agent 19 — Approval / HITL Auditor
**Model:** Claude Opus 4.6
**Scope:** `hive-swarm/swarm/nodes/approval.py`; ai-coder approval token logic (`workflow/state.py:approval_*`, `workflow/nodes.py:validate_patch_node`).

## PURPOSE
`interrupt()` correctness, `Command(resume=...)` round-trip, single-use approval tokens, `ApprovalAlreadyConsumed` guard, command-fingerprint canonicalization (SHA-256, version byte).

## PUBLIC SURFACE (verified)
- `approval_node(state) -> dict`
- `route_after_approval(state) -> str`

## WHAT WORKS ✅

### `hive-swarm/swarm/nodes/approval.py`
- `interrupt` import wrapped in `try / except` with a sane fallback that auto-approves for tests (`approval.py:L11-L17`) ✅.
- The interrupt payload deliberately excludes secrets — only `swarm_id`, objective preview, action, risk metadata, vote count, protocol (`approval.py:L40-L48`) ✅.
- Pass-through when `requires_approval=False` (`approval.py:L29-L33`) ✅.
- Decision-string normalisation: `str(payload.get("decision", "deny")).lower().strip()` (`approval.py:L52`) ✅.
- Default to "deny" if payload is missing — fail-safe ✅.
- Records the decision + risk + action preview in history (`approval.py:L54-L58`) ✅.

### `ai-coder` approval pieces (verified in fetched files)
- `WorkflowState.pending_command`, `pending_approval`, `approval_command_fingerprint`, `approval_consumed` — all present (`workflow/state.py:L139-L142`).
- `command_fingerprint(command_to_argv(command))` is called (`workflow/nodes.py:L142`) — SHA-256 over canonical argv form.
- `validate_patch_node` sets `approval_command_fingerprint` only after `command_has_shell_metacharacters` check (`workflow/nodes.py:L122-L142`) ✅ — fingerprint guards a clean argv.

## WHAT'S BROKEN 🔴

### 19-SEC1 (critical) — `hive-swarm` approval has NO single-use guard
`approval.py:L40-L48` calls `interrupt()` and reads the resume payload, but **does not** record any token / fingerprint that prevents replay. A malicious client (or a buggy retry) could resume the same `thread_id` twice with different decisions; both would route through `approval_node` and the second decision would silently override the first. The `ai-coder` code has `approval_consumed: bool` and `ApprovalAlreadyConsumed` semantics; `hive-swarm` does not.

### 19-SEC2 (high) — Approval payload echoes the proposed action without preview-truncation
`approval.py:L43`: `"proposed_action": swarm.consensus_result.action`. If the action is 50KB of generated code, the entire 50KB goes into the interrupt payload that the operator sees AND the checkpointer writes (after redaction). Recommend `swarm.consensus_result.action[:2048]` plus a `truncated: True` flag.

### 19-LG1 (high) — `interrupt()` is called inside `approval_node`, which means the node body runs **twice** on resume
LangGraph semantics: when execution hits `interrupt()`, the graph pauses; on `Command(resume=...)`, the graph re-runs the node from the top. So everything before `interrupt(...)` runs **twice**. Currently:
- `swarm = SwarmState.model_validate(state)` runs twice → fine, idempotent.
- The `if requires_approval is False` early return runs twice → fine.
- The `interrupt({...})` call returns the resume payload on the second run.

This is the correct LangGraph 0.3 pattern ✅. **But** if anyone adds a side-effecting line before `interrupt()` (e.g. `swarm.append_history(...)`), it duplicates. Add a guard comment.

### 19-SEC3 (med) — `decision == "approve"` is the only truthy branch — typo lockout possible
`approval.py:L60-L66`. If a frontend sends `{"decision": "Approve"}`, `.lower()` makes it match ✅. If it sends `{"decision": "yes"}`, falls through to deny ✅ (fail-safe). If it sends `{"decision": null}`, `str(None) = "None"` → deny ✅. **All paths fail-safe**. But a typo `{"decision": "approved"}` denies — surprising. Either accept `{"approve", "approved", "ok", "yes"}` or document the strict literal.

### 19-OBS1 (low) — On deny, `failure_cause = "approval_denied"` is set but `iteration` not incremented
A subsequent retry (if `judge_node` re-routes) would not advance `iteration`. Currently the deny path routes to END ✅, but if anyone adds a "retry on deny" flow, this becomes a bug.

## WHAT'S MISSING 🟡
- Single-use token guard (`approval_consumed: bool`).
- Approval expiry (`approval_requested_at: float`, deny if > 1 hour old).
- Multi-reviewer quorum (require 2 humans for risk > 0.95).
- Audit log of approver identity (currently anonymous).
- `Command(resume={...})` shape validation — accept any dict; should be `ApprovalDecision(decision: Literal["approve","deny"], reviewer_id: str)`.

## FIX RECOMMENDATION
```python
# approval.py — diff
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
import secrets

class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["approve", "deny"]
    reviewer_id: str = Field(..., min_length=1, max_length=128)
    decision_token: str = Field(..., min_length=16, max_length=64)

def approval_node(state):
    swarm = SwarmState.model_validate(state)
    if swarm.consensus_result is None or not swarm.consensus_result.requires_approval:
        swarm.status = "judging"
        return swarm.to_json_dict()

    # NEW: single-use guard
    if getattr(swarm, "approval_consumed", False):
        raise RuntimeError("approval already consumed for this thread")

    raw = interrupt({
        "swarm_id": swarm.swarm_id,
        "objective_preview": swarm.objective[:500],
        "proposed_action_preview": (swarm.consensus_result.action or "")[:2048],
        "action_truncated": len(swarm.consensus_result.action or "") > 2048,
        "risk_score": swarm.consensus_result.risk_score,
        "agreement_fraction": swarm.consensus_result.agreement_fraction,
        "vote_count": swarm.consensus_result.vote_count,
        "protocol": swarm.consensus_result.protocol,
        "decision_token_required": secrets.token_hex(16),  # client must echo
    })
    decision = ApprovalDecision.model_validate(raw)   # strict shape

    object.__setattr__(swarm, "approval_consumed", True)   # set guard
    # ... (rest of logic, branching on decision.decision)
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 19-SEC1 no single-use guard | **critical** | 1h |
| 19-SEC2 no payload truncation | high | 15m |
| 19-LG1 idempotency comment | low | 5m |
| 19-SEC3 strict decision literal | med | 15m |
| 19-OBS1 iteration on deny | low | 5m |
| Missing typed `ApprovalDecision` | high | 30m |
| Missing reviewer_id audit | high | 1h |
