# Agent 07 — Agent Model Auditor
**Model:** Claude Sonnet 4.6
**Scope:** `hive-swarm/swarm/models/agent.py`

## PURPOSE
Audit `AgentSpec`, `AgentState`, `AgentVote`, `WorkerResult` for immutability, success/failure invariants, vote-weight bounds.

## PUBLIC SURFACE (verified)
- `class AgentSpec(FrozenModel)` — agent_id, name, role, capabilities, metadata
- `class AgentState(HardenedModel)` — mutable per-agent runtime state
- `class AgentVote(FrozenModel)` — single immutable vote
- `class WorkerResult(FrozenModel)` — output record with `to_vote()` converter

## WHAT WORKS ✅
- `AgentSpec` is `FrozenModel` (`agent.py:L17`) — identity records correctly immutable.
- `AgentVote` is `FrozenModel` (`agent.py:L91`) — votes correctly immutable post-submission ✅ (matches PBFT spec).
- `WorkerResult` is `FrozenModel` (`agent.py:L121`) — results correctly immutable.
- `confidence: float = Field(ge=0.0, le=1.0)` bounds applied on `AgentState`, `AgentVote`, `WorkerResult` (`agent.py:L67, L95, L131`) ✅.
- `proposed_action: str = Field(min_length=1, max_length=2048)` — bounded length ✅.
- `_validate_success_consistency` model_validator enforces `success ⇒ output non-empty` AND `not success ⇒ error_message non-empty` (`agent.py:L137-L143`) ✅ — strong invariant.
- `agent_id_no_spaces` field validator (`agent.py:L25-L29`) — prevents whitespace injection that would break logging.
- `_action_not_empty` strips and rejects blank actions (`agent.py:L100-L105`) ✅.
- `to_vote()` converter (`agent.py:L153-L159`) — clean transformation, sets confidence=0 if failed ✅.

## WHAT'S BROKEN 🔴

### 07-CORR1 (med) — `_compute_output_hash` on a frozen model uses `object.__setattr__`
`agent.py:L146-L149`:
```python
@model_validator(mode="after")
def _compute_output_hash(self) -> "WorkerResult":
    if self.output and not self.output_hash:
        object.__setattr__(self, "output_hash", stable_hash(self.output))
    return self
```
This **bypasses Pydantic's frozen check** — strictly speaking it's the only legal pattern for in-validator side-effects on frozen models, **but** it means a caller who passes both `output` and an *incorrect* `output_hash` will get the incorrect hash silently kept (because the validator's check is `not self.output_hash`). Fix: always compute, never trust caller-provided hash.

### 07-T1 (low) — `metadata: dict[str, str]` rejects non-string values silently
`AgentSpec.metadata` (`agent.py:L23`) is typed as `dict[str, str]` but in Pydantic v2 a passed `dict[str, int]` will be **coerced to str** (because `model_config` does not set `strict=True`). Either tighten with `strict=True` for `AgentSpec` (it's frozen anyway) or document the coercion.

### 07-T2 (low) — `AgentState.task_context: dict[str, Any]` is unbounded
No size cap. A queen could attach a 100MB `shared_context` to a `QueenDirective`, and it'd survive every checkpoint write. Recommend `Field(max_length=10_000)` on key count, or a custom validator on serialized JSON size.

### 07-CORR2 (med) — `mark_done` does not transition out of `failed`
`agent.py:L75-L80`: if an agent is marked `failed` then later somehow `mark_done` is called, the status flips to `done`. A defensive check (`if self.status == "failed": raise RuntimeError(...)`) would prevent corrupt state. Low likelihood in current call sites but easy to add.

## WHAT'S MISSING 🟡
- No `AgentVote.signature` field. Per Agent 22 (BFT auditor), votes are unsigned — a Byzantine agent could resubmit different actions under the same `agent_id`. Add `signature: str | None = None` and an HMAC helper.
- No `AgentVote.nonce` — replay attack surface in distributed deployments.
- `WorkerResult` has no `cost_usd` / `tokens_used` — when LLM gateway is integrated, these will be needed for the dashboard.

## FIX RECOMMENDATION
```python
# agent.py — diff
@model_validator(mode="after")
def _compute_output_hash(self) -> "WorkerResult":
    if self.output:
        object.__setattr__(self, "output_hash", stable_hash(self.output))  # always compute
    return self

class AgentSpec(FrozenModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)  # tighten
    metadata: dict[str, str] = Field(default_factory=dict, max_length=64)
```

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 07-CORR1 caller-provided hash trusted | med | 5m |
| 07-T1 metadata coercion | low | 10m |
| 07-T2 task_context unbounded | low | 30m |
| 07-CORR2 mark_done after fail | low | 5m |
| Missing signature/nonce on votes | high | 1d |
