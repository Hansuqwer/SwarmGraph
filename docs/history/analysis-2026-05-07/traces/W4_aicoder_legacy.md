# Workflow W4 — `ai-coder` Legacy JSON-Artefact Fallback

**Trigger:** `ModuleNotFoundError(langgraph)` at import time → fall back to legacy JSON-artifact workflow.

## Evidence base
- `ai-coder-hardening-improved/src/ai_coder/workflow/checkpoints.py:L153-L157` raises a clear error if `local` backend selected for a LangGraph runtime, **directing the user to use the legacy AgentWorkflow path** that handles `local` automatically:
  ```python
  if backend == "local":
      raise ValueError(
          "checkpoint_backend 'local' selects the legacy JSON-artifact workflow "
          "and has no LangGraph saver. AgentWorkflow handles this automatically..."
      )
  ```
- The legacy workflow itself was **NOT fetched** in this run (likely lives in a `legacy_workflow.py` or `agent_workflow.py` not visible in the file index).

## What this trace can confirm

| Property | Status |
|---|---|
| LangGraph is optional dependency | ✅ verified — `try / except ModuleNotFoundError` at `workflow/checkpoints.py:L24-L27`, also `hive-swarm/swarm/graphs/factory.py:L23-L31`, `nodes/queen.py:L13-L17` |
| Both runtimes share `WorkflowState` schema | ✅ verified — `workflow/state.py` defines `WorkflowState` once; both runtimes import it |
| Both runtimes share validator suite | ✅ verified — same `_repo_root_must_be_safe`, `_thread_id_must_be_nonempty`, `_task_must_be_nonempty`, `_cap_lists` |
| Both runtimes produce schema-identical artefacts | ⚠️ NOT VERIFIED — legacy workflow file not in this fetch |

## What this trace cannot confirm without re-fetch

1. Whether the legacy `AgentWorkflow` actually round-trips `WorkflowState.model_dump(mode="json")` → `model_validate` losslessly.
2. Whether the legacy path emits `HistoryEntry` discriminated-union dicts or some legacy schema.
3. Whether `LocalCheckpointStore` is the only persistence layer in the legacy path.

## Action
Re-run W4 after fetching:
- `ai-coder-hardening-improved/src/ai_coder/workflow/__init__.py`
- any file matching `agent_workflow.py`, `legacy.py`, or `runtime.py` under `ai_coder/`.

## Findings linked to W4
- **DOC-aicoder-1** (low) — the legacy fallback exists per docstrings and exception messages, but is undocumented in the user-facing README sections we inspected.
- **TEST-aicoder-1** (high) — no test for "boot the legacy path with `langgraph` removed and confirm `WorkflowState` shape is identical to LangGraph runtime output".
