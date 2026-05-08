# Workflow W3 — `ai-coder` LangGraph Runtime Trace

**Path:** `plan_node → propose_patch_node → validate_patch_node → (awaiting_approval?) → run_tests_node → review_node → END | failed`

## Verified against `ai-coder-hardening-improved/src/ai_coder/workflow/nodes.py`

| Step | Node | File:Line | What happens |
|---|---|---|---|
| 1 | plan_node | `nodes.py:L40-L51` | `state.status = "planning"`; computes `prompt_hash`; calls `planner_agent`; appends `AgentHistoryEntry(kind="agent", role="planner")` |
| 2 | propose_patch_node | `nodes.py:L57-L82` | `state.status = "proposing_patch"`; calls `coder_agent` → returns `(state, patch)`. **C5 confirmed fixed**: returns `tuple[WorkflowState, PatchOutput]` so `patch` is preserved across the boundary; also `state.proposed_patch = patch.model_dump()` is stored serialised |
| 3 | validate_patch_node | `nodes.py:L88-L137` | calls `patch_ops.validate`, then security gauntlet: `command_has_shell_metacharacters`, `command_uses_disallowed_wrapper`, `denied_path_in_command`. If approval required → `status="awaiting_approval"`, sets `pending_command`, `pending_approval=True`, `approval_command_fingerprint=command_fingerprint(command_to_argv(command))` ✅ |
| 4a | awaiting_approval (W2-equivalent) | LangGraph interrupt | external resume with `Command(resume=...)` |
| 4b | run_tests_node | `nodes.py:L165-L186` | `state.status = "testing"`; runs the test command via `executor.run`; appends `ShellHistoryEntry(kind="shell", ...)` with stdout/stderr/exit_code |
| 5 | review_node | `nodes.py:L195-L220` (truncated) | `state.status = "reviewing"`; tests-passed check; revert if failed (`_revert_failed_patch(state, config, "tests_failed", patch_ops)`); else calls `reviewer_agent`; updates `state.failure_cause = "tests_failed"` if needed |
| 6 | END | — | terminal; `LocalCheckpointStore.save(state)` writes atomically (`workflow/checkpoints.py:L75-L108`) ✅ |

## C-series verification (from `ANALYSIS_AND_REVIEW.md`)

| ID | Claim | Verified status |
|---|---|---|
| **C1** | `WorkflowState` lacks `ConfigDict(extra='forbid', validate_assignment=True)` | ✅ FIXED — `workflow/state.py:L121-L124` has both flags |
| **C2** | `LocalCheckpointStore.save` not atomic | ✅ FIXED — `workflow/checkpoints.py:L93-L108` uses `tempfile.mkstemp` + `os.replace` |
| **C3** | `RedactingCheckpointer` may have method-coverage gap | ✅ ADDRESSED — all 8 methods explicitly implemented (cross-ref `agent_20_checkpointing.md`) |
| **C4** | Shell metachar regex incomplete | ✅ FIXED — `lesson.py:L26-L29` covers `! ( ) { } \n \r * ? ^ ~` |
| **C5** | `propose_patch_node` discards `PatchOutput` | ✅ FIXED — `nodes.py:L62` returns `tuple[WorkflowState, Any]` |
| **C6** | `TokenUsage` missing `Field(ge=0)` | ✅ FIXED — `workflow/state.py:L113-L114` |
| **C7** | `WorkflowState.history` unbounded | ✅ FIXED — `workflow/state.py:L172-L182` cap via model_validator |
| **C8** | `repo_root` not validated | ✅ FIXED — `workflow/state.py:L141-L150` rejects empty + `..` |
| **C9** | `fail_closed` bare `except` | ⚠️ PARTIALLY FIXED — `FailureCause` literal now includes `"unknown"` (`workflow/state.py:L52`) but the `fail_closed` function itself was not in the fetched portion of `nodes.py` (truncated at L260). Recommend re-fetch and confirm catch-all maps to `"unknown"` |
| **C10** | `history: list[dict]` schema-free | ✅ FIXED — `HistoryEntry` discriminated union (`workflow/state.py:L60-L100`) |

## M-series verification

| ID | Claim | Verified status |
|---|---|---|
| **M1** | `_ensure_model_seed` redundantly called per-node | ⚠️ NOT VERIFIED — function not in fetched code |
| **M2** | Default checkpoint backend silently `sqlite` | ✅ FIXED — `workflow/checkpoints.py:L132` defaults to `"local"` |
| **M3** | `build_graph()` is a large monolithic closure | ⚠️ NOT VERIFIED — function not in fetched code |

## `_ensure_model_seed()` runs once?
Cannot confirm — function not in fetched code. **Action**: re-fetch `nodes.py` chunk 2 + the parts that initialize seed.

## Findings linked to W3
- W3 is the **most hardened** of the three sub-projects. The C-fix track is real and verified.
- Outstanding: re-verify C9, M1, M3 from chunk 2 of `nodes.py`.
- `propose_patch_node` returns `tuple[WorkflowState, Any]` — but this is **not** the standard LangGraph node signature (which expects `state -> dict` or `state -> Command`). The runtime must be wrapping it to extract the state. Need to see the runtime to confirm the wrapping is correct.
