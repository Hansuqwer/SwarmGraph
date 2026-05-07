# Package Manifest — ai-coder-hardening-improved

## Structure

```
ai-coder-hardening-improved/
│
├── README.md                          ← Project overview + what changed
├── RESEARCH.md                        ← Comprehensive Pydantic v2 + LangGraph research
├── ANALYSIS_AND_REVIEW.md             ← Full critical review (10 critical + 5 minor findings)
├── IMPROVEMENTS_PROMPT.md             ← Master prompt for AI-assisted review & improvement
├── REPORT.html                        ← Visual HTML dashboard of all findings
├── PACKAGE_MANIFEST.md                ← This file
├── pyproject.toml                     ← Project config (hatchling, pytest, ruff, mypy)
├── create_zip.py                      ← Helper script to repackage
│
├── src/
│   └── ai_coder/
│       ├── workflow/
│       │   ├── state.py               ← WorkflowState (HARDENED: C1, C6, C7, C8, C10)
│       │   ├── checkpoints.py         ← LocalCheckpointStore + RedactingCheckpointer (HARDENED: C2, M2, M5)
│       │   └── nodes.py               ← Workflow nodes + fail_closed (HARDENED: C9)
│       └── memory/
│           └── lesson.py              ← MemoLesson (HARDENED: C4)
│
└── tests/
    ├── test_workflow_state_hardening.py    ← 25+ tests: C1, C6, C7, C8
    ├── test_memo_lesson_hardening.py       ← 20+ tests: C4
    ├── test_checkpoint_atomic_write.py     ← 15+ tests: C2
    └── test_fail_closed_comprehensive.py  ← 8 tests: C9
```

## Issue → Fix → Test Traceability

| Issue | Severity | File Fixed | Test File |
|---|---|---|---|
| C1: WorkflowState no ConfigDict | 🔴 Critical | workflow/state.py | test_workflow_state_hardening.py::TestExtraForbid, TestValidateAssignment |
| C2: Non-atomic checkpoint writes | 🔴 Critical | workflow/checkpoints.py | test_checkpoint_atomic_write.py |
| C4: Incomplete metachar denylist | 🔴 Critical | memory/lesson.py | test_memo_lesson_hardening.py::TestUnsafeSummaries |
| C6: TokenUsage no bounds | 🔴 Critical | workflow/state.py | test_workflow_state_hardening.py::TestTokenUsageBounds |
| C9: fail_closed no catch-all | 🔴 Critical | workflow/nodes.py | test_fail_closed_comprehensive.py |
| C10: Untyped history list | 🔴 Critical | workflow/state.py | test_workflow_state_hardening.py::TestBoundedLists |
| C7: Unbounded lists | 🟠 High | workflow/state.py | test_workflow_state_hardening.py::TestBoundedLists |
| C8: repo_root not validated | 🟠 High | workflow/state.py | test_workflow_state_hardening.py::TestRepoRootValidation |
| M2: Wrong default backend | 🟡 Medium | workflow/checkpoints.py | (config-level) |
| M5: serde=None handling | 🟡 Medium | workflow/checkpoints.py | (integration-level) |

## Running Tests

```bash
# Install dependencies
pip install pydantic>=2.7.0 pytest>=8.0

# Run all new tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_workflow_state_hardening.py -v
pytest tests/test_memo_lesson_hardening.py -v
pytest tests/test_checkpoint_atomic_write.py -v
pytest tests/test_fail_closed_comprehensive.py -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```
