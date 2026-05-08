# Agent 02 — Repo Topology Mapper
**Model:** Claude Sonnet 4.6
**Scope:** every file in `swarmMain/`
**Deliverable goal:** full file tree + LOC + import graph + dead-file list.

## PURPOSE
Establish a comprehensive map of the repo so every other agent knows exactly what's in scope.

## REPO TREE (verified)

```
swarmMain/
├── hive-swarm/                                  ★ core framework
│   ├── MISSION_LOCK.md                          (~3 KB doc)
│   ├── HIVE_LEADER_SYNTHESIS.md                 (~9 KB doc)
│   ├── pyproject.toml                           (16 lines)
│   ├── swarm/
│   │   ├── __init__.py                          (62 lines, public API)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                          (~75 lines)
│   │   │   ├── types.py                         (~75 lines)
│   │   │   ├── agent.py                         (~155 lines)
│   │   │   ├── task.py                          (~115 lines)
│   │   │   ├── config.py                        (~80 lines)
│   │   │   ├── consensus.py                     (~210 lines)
│   │   │   ├── memory.py                        (~205 lines)
│   │   │   └── state.py                         (~245 lines)
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── router.py                        (~110 lines)
│   │   │   ├── queen.py                         (~165 lines)
│   │   │   ├── worker.py                        (~135 lines)
│   │   │   ├── consensus.py                     (~80 lines)
│   │   │   ├── judge.py                         (~70 lines)
│   │   │   ├── approval.py                      (~80 lines)
│   │   │   ├── sona.py                          (~100 lines)
│   │   │   └── checkpointing.py                 (~145 lines)
│   │   └── graphs/
│   │       ├── __init__.py
│   │       └── factory.py                       (~165 lines)
│   └── tests/
│       ├── test_models.py                       (~20 tests)
│       ├── test_consensus.py                    (~20 tests)
│       ├── test_topologies.py                   (~15 tests)
│       ├── test_sona_memory.py                  (~15 tests)
│       └── test_e2e.py                          (~15 tests)
│
├── ai-coder-hardening-improved/
│   ├── ANALYSIS_AND_REVIEW.md                   (≈ self-audit, C1–C10, M1–M3)
│   ├── IMPROVEMENTS_PROMPT.md
│   ├── PACKAGE_MANIFEST.md
│   ├── README.md
│   ├── REPORT.html
│   ├── RESEARCH.md
│   ├── create_zip.py
│   ├── pyproject.toml
│   ├── src/ai_coder/
│   │   ├── __init__.py
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   └── lesson.py                        (~120 lines, MemoLesson hardened)
│   │   └── workflow/
│   │       ├── __init__.py
│   │       ├── checkpoints.py                   (~190 lines, atomic writes)
│   │       ├── nodes.py                         (~280 lines)
│   │       └── state.py                         (~210 lines, hardened)
│   └── tests/
│
├── ai-provider-swarm-gateway/
│   ├── .env.example
│   ├── ARCHITECTURE.md
│   ├── COMPLIANCE.md                            ⚠ EXCLUDED FROM ANALYSIS (per policy)
│   ├── MISSION_LOCK.md
│   ├── PROJECT_REVIEW.md
│   ├── PROVIDER_REGISTRY.md
│   ├── README.md
│   ├── SETUP.md
│   ├── pyproject.toml
│   └── src/ai_provider_swarm_gateway/
│       ├── __init__.py
│       ├── cli.py
│       ├── consensus/strategies.py
│       ├── dashboard/app.py
│       ├── graph/{builder.py, nodes.py}         (nodes ~290 lines)
│       ├── models/{provider,state,quota,credentials}.py
│       ├── policy/guardrails.py
│       ├── providers/{base, anthropic, deepseek, glm, google, groq, kimi, mock, openai, openrouter, qwen}_adapter.py
│       ├── quota/tracker.py                     (~110 lines)
│       └── registry/{providers.yaml, loader.py} (yaml ≈ 22 providers)
│
└── ruflo-swarm-prompt/
    ├── RUFLO_RESEARCH_NOTES.md
    └── RUFLO_SWARM_PYDANTIC_LANGGRAPH_PROMPT.md
```

**Approx total LoC (Python only):** ~3,500
**Approx total tests:** ~85 (claimed) — coverage unverified by Agent 04.

## IMPORT GRAPH (Mermaid — see `mermaid/import_graph.md`)

The graph is a clean DAG (no cycles detected). Highlights:
- `swarm/__init__.py` imports from every sibling module (public API surface).
- `nodes/*.py` import from `models/*.py` (one-way).
- `graphs/factory.py` imports from `nodes/*.py` (one-way).
- No circular import risk.

## DEAD FILES / UNUSED CODE
- `nodes/queen.py:L9` imports `secrets` but never uses it — dead import (low).
- `nodes/checkpointing.py:L7` imports `secrets` and uses it (kept). ✅
- `models/memory.py:L11` imports `time` but only uses `time.time` via `default_factory=time.time` — kept ✅.
- No unused public symbols detected via grep on `__all__` ✅.

## DUPLICATIONS
- `_cap_lists` model_validator pattern duplicated in `hive-swarm/swarm/models/state.py:L116-L121` and `ai-coder-hardening-improved/.../workflow/state.py:L172-L182` — candidate for shared `bounded_list` helper.
- Atomic-write pattern duplicated in `hive-swarm/swarm/nodes/checkpointing.py:L78-L91` and `ai-coder-hardening-improved/.../workflow/checkpoints.py:L93-L108` — candidate for shared `atomic_write_json()` helper.
- `RedactingCheckpointer` class duplicated (different impls) — see Agent 20.

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| Dead `secrets` import | low | 1m |
| 3 duplications | med | 1d (extract `swarm-shared` package) |
