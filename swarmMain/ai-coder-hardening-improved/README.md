# AI Coder — Hardened Edition (Improved)

Hardened AI coding agent prototype with checkpointed LangGraph workflows, typed agent boundaries,
policy-gated shell execution, secret redaction, and conservative release controls.

This fork contains **critical security and correctness improvements** identified through comprehensive
code review. See [`ANALYSIS_AND_REVIEW.md`](ANALYSIS_AND_REVIEW.md) for the full findings.

---

## What Changed

### 🔴 Critical Fixes

| ID | File | Fix |
|---|---|---|
| C1 | `workflow/state.py` | `WorkflowState` now has `ConfigDict(extra='forbid', validate_assignment=True)` — unknown checkpoint fields are rejected; mutations are validated |
| C2 | `workflow/checkpoints.py` | `LocalCheckpointStore.save()` uses atomic temp-file + `os.replace()` — no more corrupt checkpoints on crash; bad JSON raises `CheckpointCorrupt` not raw `JSONDecodeError` |
| C4 | `memory/lesson.py` | `MemoLesson.summary` validator expanded to cover `! ( ) { } \n \r * ? ^ ~` in addition to original metachar set |
| C6 | `workflow/state.py` | `TokenUsage` fields have `ge=0` — negative token counts rejected |
| C9 | `workflow/nodes.py` | `fail_closed()` always sets `failure_cause` — unknown exceptions map to `'unknown'` instead of leaving it `None` |
| C10 | `workflow/state.py` | `history` list uses typed `HistoryEntry` discriminated union (validation-ready) |

### 🟠 High Priority Fixes

| ID | File | Fix |
|---|---|---|
| C7 | `workflow/state.py` | `history`, `errors`, `model_errors` lists bounded by `_MAX_HISTORY_ENTRIES` / `_MAX_ERRORS` via model validator |
| C8 | `workflow/state.py` | `repo_root`, `thread_id`, `task` have field validators (non-empty, no traversal) |

### 🟡 Medium Fixes

| ID | File | Fix |
|---|---|---|
| M2 | `workflow/checkpoints.py` | Default checkpoint backend changed from `sqlite` to `local` to match documented quickstart |
| M5 | `workflow/checkpoints.py` | `RedactingCheckpointer` handles `serde=None` safely |

---

## Quick Start (macOS Apple Silicon — M1/M2/M3/M4)

```bash
unzip ai-coder-hardening.zip
cd ai-coder-hardening
./install-macos.sh --dev
```

Then:

```bash
source .venv/bin/activate
ai-coder doctor
ai-coder init --repo .
pytest -q
```

---

## Running the New Tests

```bash
# All tests
pytest tests/ -q

# Specific hardening tests
pytest tests/test_workflow_state_hardening.py -v
pytest tests/test_memo_lesson_hardening.py -v
pytest tests/test_checkpoint_atomic_write.py -v
pytest tests/test_fail_closed_comprehensive.py -v
```

---

## Architecture

```
src/ai_coder/
├── workflow/
│   ├── state.py          ← WorkflowState (Pydantic v2, hardened)
│   ├── graph.py          ← AgentWorkflow orchestrator
│   ├── langgraph_runtime.py  ← LangGraph facade
│   ├── checkpoints.py    ← LocalCheckpointStore + RedactingCheckpointer (hardened)
│   ├── nodes.py          ← plan/propose/validate/apply/test/review/fail_closed (hardened)
│   └── adapters.py       ← Side-effect adapters
├── memory/
│   └── lesson.py         ← MemoLesson (Pydantic v2, hardened validator)
├── replay/
│   ├── types.py          ← ReplayError hierarchy + RecordedCall
│   ├── recorder.py       ← Sidecar recording
│   ├── replayer.py       ← Deterministic replay
│   └── contract.py       ← Workflow-level replay contract hashes
└── ...
```

---

## Security Invariants

These invariants are preserved and tested:

1. **Checkpoint canonical invariant**: Checkpoints store canonical state (paths not redacted) for LangGraph resumption. Redaction at artifact/log sinks only.

2. **Approval token single-use invariant**: `ApprovalStore.consume()` called exactly once per approval. `ApprovalAlreadyConsumed` handled at every call site.

3. **Fail-closed invariant**: Every model gateway error transitions state to `failed` or `model_unavailable`. `failure_cause` is always set.

4. **Shell safety invariant**: No command executed without `command_has_shell_metacharacters()` + `denied_path_in_command()`.

5. **Atomic write invariant**: Checkpoint files written via temp-file + `os.replace()` — never partially corrupt.

---

## Research References

- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [`RESEARCH.md`](RESEARCH.md) — comprehensive Pydantic v2 + LangGraph research notes
- [`ANALYSIS_AND_REVIEW.md`](ANALYSIS_AND_REVIEW.md) — full critical review with 10 critical + 5 minor findings
- [`IMPROVEMENTS_PROMPT.md`](IMPROVEMENTS_PROMPT.md) — master prompt for further AI-assisted review
