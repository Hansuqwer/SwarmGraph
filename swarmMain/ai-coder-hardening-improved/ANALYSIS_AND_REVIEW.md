# Critical Analysis & Review: ai-coder-hardening

## Executive Summary

`ai-coder-hardening` is a **hardened AI coding agent** built on:
- **LangGraph** for stateful, checkpointed, interruptible workflow orchestration
- **Pydantic v2** for typed agent boundaries, state validation, and memory schema enforcement
- **LiteLLM / PydanticAI** model gateways with fail-closed routing
- **Custom security layers**: secret redaction, MCP allowlist, approval-gate tokens, shell-metachar guards

The project demonstrates **strong security thinking** and **architectural maturity** for a prototype. Below is a comprehensive critical review followed by concrete improvements implemented in this package.

---

## Strengths ✅

### 1. Excellent Use of Pydantic v2 for Typed Boundaries
- `WorkflowState(BaseModel)` with `Literal` union types (`WorkflowStatus`, `FailureCause`) ensures exhaustive, validated state machines
- `MemoLesson` is a textbook example of security-first validation: glob traversal guards, shell metachar rejection, URL prohibition — all via `@field_validator`
- `model_dump(mode='json')` used consistently for JSON serialization
- `model_validate()` used for round-trip checkpoint deserialization

### 2. Principled LangGraph Integration
- `RedactingCheckpointer(BaseCheckpointSaver)` wraps every LangGraph saver with secret redaction on write paths — without breaking read paths
- `interrupt()` used correctly for human-in-the-loop approval gate
- `Command(resume=...)` used for resumption
- Multiple backends (memory/sqlite/postgres) with a clean `build_checkpointer()` factory
- Proper `close_checkpointer()` / context manager teardown

### 3. Security Architecture
- Two-surface redaction model: artifact/log boundary (full redaction) vs checkpoint boundary (secret-only redaction, paths preserved for resumption)
- Approval tokens are single-use, per-command, with `ApprovalAlreadyConsumed` guard
- Command fingerprints use versioned JSON canonicalization (`{"v":1,"argv":[...]}`) with SHA-256
- Shell metacharacter detection before any command execution
- `denied_path_in_command` prevents commands touching credential paths

### 4. Dual-Runtime Strategy
- Graceful fallback: LangGraph runtime → legacy JSON-artifact workflow when LangGraph is unavailable
- `ModuleNotFoundError` caught at import time, not at usage time

---

## Critical Issues & Gaps 🔴

### C1. `WorkflowState` Lacks `model_config` Hardening
**Problem**: `WorkflowState` uses `BaseModel` with no `ConfigDict`. This means:
- Extra fields are silently ignored (`extra='ignore'` default) — a deserialization attack surface
- No `validate_assignment=True` — mutations to state fields bypass validators
- `revalidate_instances` not set — stale instances can hold invalid data

**Impact**: If a checkpoint JSON contains extra keys injected by an attacker or a schema drift, they silently pass through.

**Fix**: Add `model_config = ConfigDict(extra='forbid', validate_assignment=True)`

### C2. `LocalCheckpointStore.save()` Has No Atomic Write
**Problem**: `checkpoint_path.write_text(...)` is not atomic. A crash mid-write leaves a corrupt JSON file. On resume, this raises an unhandled `json.JSONDecodeError`, not the clean `CheckpointNotFound`.

**Fix**: Write to a `.tmp` file then `os.replace()` (atomic on POSIX).

### C3. `RedactingCheckpointer` Has No Coverage Guard for New LangGraph Methods
**Problem**: The `__getattr__` proxy was removed (correctly, per commit message) but the coverage test that guards against future LangGraph method additions is referenced in commit messages but its effectiveness depends on LangGraph's public API stability. If LangGraph adds a new write method, it silently bypasses redaction.

**Fix**: Add a `__init_subclass__` hook or a CI-level check that validates all `BaseCheckpointSaver` abstract methods are explicitly implemented.

### C4. `MemoLesson.summary` Regex Is Incomplete
**Problem**: The shell metachar regex `r"[;&|<>\\`$]"` misses:
- `!` (history expansion in bash)
- `(` and `)` (subshell grouping)
- `{` and `}` (brace expansion)
- Newlines (`\n`, `\r`) — can terminate a command context

**Fix**: Expand the denylist or use a more comprehensive approach.

### C5. `propose_patch_node` Loses the `PatchOutput` in LangGraph Runtime
**Problem**: In `langgraph_runtime.py`, the `propose_patch` node captures `_patch` but discards it:
```python
def _node(s: WorkflowState) -> WorkflowState:
    next_state, _patch = propose_patch_node(s, ...)
    return next_state  # _patch is lost!
```
The `validate_patch` node reconstructs `PatchOutput` from state via `_patch_from_state()`. This reconstruction is a second serialization/deserialization round-trip that could drift if `PatchOutput` gains new required fields.

**Fix**: Store `PatchOutput` as a serialized field in `WorkflowState` or thread it through LangGraph's state explicitly.

### C6. `TokenUsage` Has No Bounds Validation
**Problem**: `TokenUsage(input_tokens=0, output_tokens=0)` accepts negative integers. A buggy gateway could record `input_tokens=-1`, silently corrupting usage accounting.

**Fix**: Add `Field(ge=0)` constraints.

### C7. `history` List Is Unbounded
**Problem**: `WorkflowState.history: list[dict]` grows forever. In long-running or retried workflows, this can balloon checkpoint size and exhaust memory/storage.

**Fix**: Apply `_cap_state_history()` consistently (it's called in `LangGraphRuntime._export_result` but **not** in `LocalCheckpointStore.save` or `_legacy_start`).

### C8. `WorkflowState.repo_root` Is a Bare `str`, Not Validated
**Problem**: `repo_root: str` has no path validation — it could be an empty string, a relative path, or a path with `..` traversal. The `LocalCheckpointStore` does `Path(repo_root).resolve()` but `WorkflowState` itself doesn't guard it.

**Fix**: Use a `field_validator` or `Annotated` type to validate `repo_root` is non-empty and absolute.

### C9. `fail_closed` Node Has Incomplete `FailureCause` Mapping
**Problem**: `fail_closed()` in `nodes.py` maps `ModelGatewayAuthError` → `auth_failed`, `ModelGatewayRateLimited` → `rate_limited`, etc., but falls through to a bare `except Exception` that sets status to `failed` without a `failure_cause`. This means monitoring/alerting can't distinguish between "unexpected exception" and "known failure modes".

**Fix**: Add a catch-all `failure_cause = "unknown"` and log the exception type for observability.

### C10. No Pydantic Model for `history` Entries
**Problem**: `history: list[dict[str, Any]]` is schema-free. History entries with `kind="shell"`, `kind="agent"`, `kind="patch_validation"` etc. have no typed contract. This makes them impossible to validate, evolve safely, or introspect reliably.

**Fix**: Introduce a discriminated union `HistoryEntry = Annotated[Union[ShellEntry, AgentEntry, PatchEntry, MemoryEntry], Field(discriminator='kind')]`.

---

## Minor Issues 🟡

### M1. `_ensure_model_seed` Is Called Multiple Times Redundantly
The `plan_node`, `propose_patch_node`, and `review_node` all call `_ensure_model_seed()`. If the seed is set once in `WorkflowState.seed`, it should be initialized once at workflow start, not re-checked per node.

### M2. `checkpoint_backend_from_raw` Defaults to `sqlite` Silently
If `workflow.checkpoint_backend` is missing from config, it defaults to `"sqlite"`. This is surprising — `"local"` might be more appropriate as a default that matches the documented quickstart behavior.

### M3. `build_graph()` Is a Large Closure
`build_graph()` defines 8+ nested functions with closures over config, model_config, executor, approvals, side_effects. This makes the function hard to test in isolation and difficult to extend. Consider extracting nodes into a `WorkflowNodes` class.

### M4. Event Correlation IDs Are Always `thread_id`
`correlation_id=state.thread_id` is used everywhere, making it impossible to correlate events within a single thread execution vs across executions of the same thread.

### M5. `RedactingCheckpointer` Inherits `BaseCheckpointSaver` But Wraps `serde` Conditionally
`super().__init__(serde=getattr(inner, "serde", None))` — if `inner` has no `serde`, the parent gets `None`. This could cause serialization failures in LangGraph versions that require a non-None serde.

---

## Improvement Recommendations

| Priority | Issue | Recommendation |
|---|---|---|
| 🔴 Critical | C1 WorkflowState config | Add `ConfigDict(extra='forbid', validate_assignment=True)` |
| 🔴 Critical | C2 Atomic writes | Use temp-file + `os.replace()` in `LocalCheckpointStore.save` |
| 🔴 Critical | C6 TokenUsage bounds | Add `ge=0` to `input_tokens`, `output_tokens` |
| 🔴 Critical | C10 Untyped history | Introduce `HistoryEntry` discriminated union |
| 🟠 High | C4 MemoLesson regex | Expand shell metachar denylist |
| 🟠 High | C7 Unbounded history | Apply `_cap_state_history` in legacy path too |
| 🟠 High | C9 fail_closed mapping | Add catch-all `failure_cause` |
| 🟡 Medium | C5 PatchOutput loss | Store serialized patch in WorkflowState |
| 🟡 Medium | C8 repo_root validation | Add field validator for path safety |
| 🟡 Medium | M3 build_graph closure | Extract to `WorkflowNodes` class |
| 🟢 Low | M4 correlation IDs | Generate per-execution correlation IDs |
| 🟢 Low | M2 backend default | Document and assert default backend |
