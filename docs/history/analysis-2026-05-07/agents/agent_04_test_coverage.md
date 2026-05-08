# Agent 04 — Test-Strategy Auditor
**Model:** Claude Opus 4.7
**Scope:** `*/tests/`, conftests, fixtures
**Deliverable goal:** per-module coverage estimate + missing edge cases + smell list + property-based gaps.

## PURPOSE
Verify the "70+ tests across 5 suites" claim from `HIVE_LEADER_SYNTHESIS.md` is real, current, and covers the claims.

## EVIDENCE BASE
- `hive-swarm/tests/test_models.py` (≈ 20 tests, claimed)
- `hive-swarm/tests/test_consensus.py` (≈ 20 tests, claimed)
- `hive-swarm/tests/test_topologies.py` (≈ 15 tests, claimed)
- `hive-swarm/tests/test_sona_memory.py` (≈ 15 tests, claimed)
- `hive-swarm/tests/test_e2e.py` (≈ 15 tests, claimed)
- `ai-coder-hardening-improved/tests/` (count unverified)

## ESTIMATED COVERAGE (no live run; static reasoning)

| Module | Functions / classes | Likely covered | Coverage est. |
|---|---|---|---|
| `models/base.py` | `stable_hash`, `now_ts`, `HardenedModel`, `FrozenModel` | construction tests | ~70% |
| `models/types.py` | Literal aliases | implicit via consumers | ~100% |
| `models/agent.py` | `AgentSpec`, `AgentState`, `AgentVote`, `WorkerResult`, validators | strong likely | ~85% |
| `models/task.py` | `SwarmTask`, `QueenDirective`, lifecycle | strong likely | ~80% |
| `models/config.py` | `SwarmConfig`, validators | likely tested | ~80% |
| `models/consensus.py` | 4 protocols + `run_consensus` | claimed 20 tests | **~60%** (see below) |
| `models/memory.py` | `SwarmMemory`, `SwarmMemoryEntry`, `VectorMemoryAdapter`, `HybridMemorySearch` | claimed 15 SONA tests | ~70% |
| `models/state.py` | `SwarmState`, `SwarmCheckpoint`, drift, mutations | claimed e2e tests | ~75% |
| `nodes/router.py` | `estimate_complexity`, `route_task`, `router_node` | claimed topology tests | ~80% |
| `nodes/queen.py` | 5 decompose fns + `queen_node` + 2 stubs | claimed topology tests | ~70% |
| `nodes/worker.py` | role dispatch + `worker_node` + `collect_results_node` | likely covered | ~70% |
| `nodes/consensus.py` | `consensus_node`, `route_after_consensus` | likely covered | ~80% |
| `nodes/judge.py` | `judge_node`, `route_after_judge` | likely covered | ~75% |
| `nodes/approval.py` | `approval_node`, `route_after_approval` | **probably weak** (no HITL fixture seen) | ~40% |
| `nodes/sona.py` | `distill_node`, `memory_retrieve_node` | claimed SONA tests | ~70% |
| `nodes/checkpointing.py` | 2 stores + `SwarmRedactingCheckpointer` | likely partial | **~50%** (8 BaseCheckpointSaver methods, see Agent 20) |
| `graphs/factory.py` | `build_swarm_graph`, `_build_mock_graph`, `_MockCompiledGraph` | claimed e2e tests | ~70% |

**Overall framework coverage estimate:** ≈ 70% (line) / **≈ 50% (branch)**

## WHAT'S BROKEN 🔴

### 04-T1 (high) — No property-based / fuzz tests for consensus
`models/consensus.py` has 4 protocols with non-trivial math (`math.ceil`, weighted floats). Standard 20 unit tests cover named cases but not:
- Liveness under random faulty subsets (BFT)
- Convergence over N rounds (Gossip)
- Idempotence (Majority twice = same result)
- Tie-break stability (Majority with permuted vote order)

Recommend `hypothesis>=6.110`-based suite. ETA: 1d.

### 04-T2 (critical) — No `RedactingCheckpointer` coverage-guard test
There is no test that asserts `SwarmRedactingCheckpointer` overrides every abstract method of `BaseCheckpointSaver`. If LangGraph adds a new abstract method in 0.4 (e.g. `bulk_put`), the next version bump silently leaks unredacted writes. See Agent 20 for the recipe.

### 04-T3 (high) — No HITL `interrupt()` + `Command(resume=...)` integration test
`nodes/approval.py:L28-L62` uses `interrupt()` + reads `payload["decision"]`. There is no e2e test that:
1. Drives the graph until interrupt fires.
2. Resumes with `Command(resume={"decision": "approve"})`.
3. Asserts state continues correctly.

The mock at `approval.py:L20` returns `{"decision": "approve"}` unconditionally — not the same as exercising real HITL.

### 04-T4 (high) — No round-trip fuzz on `SwarmState` / `WorkflowState`
The framework is built on `to_json_dict()` / `from_json_dict()` round-trips at every node boundary. We need:
```python
@given(st.builds(SwarmState, ...))
def test_roundtrip(state):
    assert SwarmState.from_json_dict(state.to_json_dict()) == state
```
Not present.

### 04-T5 (med) — No "all 8 LangGraph BaseCheckpointSaver methods called by graph" test
Not detected.

### 04-T6 (med) — No multi-process concurrency test on `QuotaTracker`
`ai-provider-swarm-gateway/.../quota/tracker.py` writes JSON via `Path.write_text` (NOT atomic). Two concurrent processes will race. No test exercises this. See Agent 29.

### 04-T7 (low) — No fixture file for `pytest-asyncio` mode (auto vs strict)
Without `[tool.pytest.ini_options].asyncio_mode = "auto"` (or `strict`), async tests will produce deprecation warnings on `pytest-asyncio>=0.23`.

## WHAT'S MISSING 🟡
- `tests/conftest.py` not detected — likely missing shared fixtures.
- No `tests/snapshots/` for golden outputs.
- No mutation-testing config (`mutmut` / `cosmic-ray`).
- No CI manifest, so coverage reports are not enforced.
- `ai-coder-hardening-improved/tests/` content not fetched in this run.

## TEST SMELLS (from naming / claimed counts)
- `test_models.py: 20 tests` for 6 model files = ~3.3 tests/file → pure smoke; not enough for the validators.
- `test_e2e.py: 15 tests` for a 7-edge graph + 5 topologies = combinatorially under-covered (5 × 4 consensus × 3 tiers = 60 cells, only 15 sampled).

## FIX RECOMMENDATION
1. Add `tests/test_property_consensus.py` using Hypothesis (target 04-T1).
2. Add `tests/test_redaction_coverage.py` (target 04-T2).
3. Add `tests/test_hitl_resume.py` with a real `InMemorySaver` checkpointer (target 04-T3).
4. Add `tests/test_state_roundtrip.py` (target 04-T4).
5. Add `tests/test_quota_concurrent.py` using `multiprocessing.Pool` (target 04-T6).
6. Add `tests/conftest.py` with shared `make_state()`, `make_config()` builders.

## SEVERITY × EFFORT
| Finding | S | E |
|---|---|---|
| 04-T1 property tests | high | 1d |
| 04-T2 coverage guard | critical | 1h |
| 04-T3 HITL integration | high | 1d |
| 04-T4 round-trip fuzz | high | 1d |
| 04-T6 quota concurrency | high | 1h |
