# Workflow W2 — `hive-swarm` HITL (Human-In-The-Loop) Path

**Path:** `... → consensus_node (risk≥0.8) → approval_node → interrupt() → external resume → Command(resume={"decision": ...}) → judge_node → ...`

## Trigger condition

`requires_approval=True` is set inside `run_consensus` (`models/consensus.py:L213-L226`):
```python
risk = 1.0 - result.agreement_fraction if not result.failed else 1.0
requires_approval = risk >= risk_threshold   # default risk_threshold = 0.8
```

So HITL fires when **agreement_fraction ≤ 0.20**. Per Agent 11, this is unusually loose — most users would expect HITL at agreement < 0.7.

## Step-by-step trace

| Step | Node | File:Line | What happens |
|---|---|---|---|
| A | consensus_node | `nodes/consensus.py:L51-L53` | sets `swarm.status = "awaiting_approval"` when `result.requires_approval=True` |
| B | route_after_consensus | `consensus.py:L67-L73` | reads `swarm.status` → returns `"approval_node"` |
| C | approval_node entry | `nodes/approval.py:L29-L33` | guard: if `consensus_result is None or not requires_approval` → pass through (defensive) |
| D | interrupt() | `approval.py:L40-L48` | builds payload: `swarm_id, objective, proposed_action, risk_score, agreement_fraction, vote_count, protocol`. **19-SEC2 high**: action not preview-truncated |
| — | (graph pauses; checkpoint saved) | LangGraph runtime | requires `checkpointer` configured (it is, by default `SwarmRedactingCheckpointer(InMemorySaver())` in `factory.py:L126-L130`) |
| E | external resumer | user code | `graph.invoke(Command(resume={"decision": "approve"}), config={"configurable": {"thread_id": "..."}})` |
| F | approval_node resume | `approval.py:L40` | the `interrupt(...)` call returns the resume payload. Node body re-runs from top up to `interrupt()` (LangGraph semantics) — see 19-LG1 |
| G | decision parsing | `approval.py:L52` | `decision = str(payload.get("decision", "deny")).lower().strip()` — fail-safe to deny ✅ |
| H | history + status update | `approval.py:L54-L66` | writes `approval_decision` history entry; sets `status="judging"` (approve) or `status="denied"` + `failure_cause="approval_denied"` (deny) |
| I | route_after_approval | `approval.py:L72-L75` | `denied → "end"` else `→ "judge_node"` |

## Single-use? Fingerprint? Expiry?

| Property | hive-swarm `approval_node` | ai-coder approval logic |
|---|---|---|
| Single-use guard | ❌ NONE — finding **19-SEC1 critical** | ✅ `WorkflowState.approval_consumed: bool` (`workflow/state.py:L142`) |
| Command fingerprint | ❌ none | ✅ `WorkflowState.approval_command_fingerprint` (`workflow/state.py:L141`) bound to SHA-256 of canonical argv |
| Expiry | ❌ none | ❌ none |
| Reviewer ID logged | ❌ anonymous | ❌ anonymous |
| Multi-reviewer quorum | ❌ none | ❌ none |
| Strict decision shape | ❌ accepts any dict | ⚠️ better but also dict |

**Verdict:** `hive-swarm` HITL path is functional but **lacks every production-grade safety check** that `ai-coder` already implements. Cross-port the `approval_consumed` + `approval_command_fingerprint` pattern. See Fix Plan items F-19A, F-19B, F-19C.

## `Command(resume=token)` round-trip

| Stage | Token-bound? |
|---|---|
| approval payload includes a server-issued nonce | ❌ no (recommended in `agent_19_approval.md` fix sketch) |
| client must echo nonce in resume | ❌ no |
| state validates nonce matches before accepting decision | ❌ no |

A malicious or misconfigured retry can resume the same `thread_id` twice with conflicting decisions. **Risk class: critical for any production deployment with > 1 reviewer.**

## Findings linked to W2
- **19-SEC1 (critical)** — no single-use guard
- **19-SEC2 (high)** — payload not truncated
- **19-LG1 (low)** — node body runs twice (LangGraph normal)
- Missing: typed `ApprovalDecision` Pydantic model for the resume shape

## Test gap (linked to Agent 04)
- **04-T3** — no e2e test that drives interrupt → resume → continue with a real `InMemorySaver` checkpointer. The fallback `interrupt()` stub in `approval.py:L15-L17` auto-approves; tests using the mock graph never exercise the deny path.
