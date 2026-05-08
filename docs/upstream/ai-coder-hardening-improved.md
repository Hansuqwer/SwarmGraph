# Patch note — ai-coder-hardening-improved (2026-05-07)

## Status

The C1–C10 / M2 fix set from `ANALYSIS_AND_REVIEW.md` was **already verified merged**
in the source we audited (`agents/agent_09_state.md`, `agent_12_memory_models.md`,
`agent_20_checkpointing.md`, `traces/W3_aicoder_langgraph.md`).

This sub-project is the most-hardened of the three at the audit baseline. The
hive orchestrator's responsibility for this run is therefore reduced to:

1. Vendor `swarm-shared/` so the (already-correct) atomic-write and redaction
   patterns can converge with `hive-swarm`. **DONE** — see
   `swarmMain_patched/swarm-shared/`.

2. Add the missing `swarm_shared` dep to this project's pyproject when re-fetched.
   **DEFERRED** (RR2/RR3 — `pyproject.toml` not in the workspace fetch).

## Items still outstanding (require RR2 / RR3 re-fetch)

| Item | Why deferred |
|---|---|
| C9 verification (`fail_closed` catch-all → `failure_cause="unknown"`) | `workflow/nodes.py` chunk 2 not in the analysis fetch |
| M1 verification (`_ensure_model_seed` called once, not per-node) | Same |
| M3 verification (`build_graph()` decomposed) | Same |
| Legacy `AgentWorkflow` schema parity (W4 trace) | Legacy file not in the fetch |

## Forward-port suggestions for the next hive run

- Replace `LocalCheckpointStore.save`'s atomic-write block with
  `from swarm_shared.atomic_write import atomic_write_json`
  (eliminates the duplicated `tempfile.mkstemp + os.replace` block at
  `workflow/checkpoints.py:L93-L108`).
- Replace `_redact_checkpoint_obj` with `swarm_shared.redaction.Redactor.redact`
  (the ai-coder Redactor is already production-grade; this just consolidates).
- Add `from swarm_shared.checkpointing import BaseRedactingCheckpointer` and
  switch `RedactingCheckpointer` to subclass it (keep the ai-coder-specific
  artefact-vs-checkpoint redaction policies as kwargs).

None of these break the existing API; all are pure refactors guarded by the
existing test suite.
