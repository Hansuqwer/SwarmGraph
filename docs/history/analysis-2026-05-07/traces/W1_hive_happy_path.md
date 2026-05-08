# Workflow W1 — `hive-swarm` Happy Path Trace

**Path:** `SwarmConfig → SwarmState → build_swarm_graph() → memory_retrieve → router → queen (Send) → workers → collect → consensus → judge → SONA distill → END`

## Step-by-step trace (ground truth code)

| Step | Node | File:Line | What happens | State delta |
|---|---|---|---|---|
| 0 | construction | user code | `SwarmConfig(topology="hierarchical", consensus_protocol="raft")` then `SwarmState(swarm_id="S1", objective="Implement OAuth2", config=...)`; `_auto_objective_hash` validator computes `objective_hash = stable_hash(objective)[:16]` | `objective_hash` set; `status="initializing"` |
| 1 | START → memory_retrieve | `factory.py:L80` | `memory_retrieve_node(state)` runs; if `sona_enabled` searches memory for objective patterns; promotes scores. **27-LG1**: retrieved patterns NOT injected into state — no downstream visibility | `history` += `memory_retrieve` entry |
| 2 | memory_retrieve → route_task | `factory.py:L81` | `router_node(state)` computes `complexity_score` via heuristic, sets `complexity_tier` | `status="routing"`, `complexity_score` set |
| 3 | route_task → \<topology\>_queen | `factory.py:L82-L88` (cond. edge) | `route_task(state)` returns the queen-name string for `tier3_swarm` + topology="hierarchical" → `"hierarchical_queen"`. **14-CORR1**: most realistic objectives land in tier3 due to keyword heuristic biases | routes to `hierarchical_queen` |
| 4 | hierarchical_queen | `queen.py:L86-L144` | `queen_node` decomposes into 5 role-specific tasks (researcher, architect, coder, tester, reviewer); creates `AgentSpec` × 5, `SwarmTask` × 5, `QueenDirective` × 5; returns `list[Send("worker_node", agent_state.to_json_dict())]` × 5 | `agents`, `tasks` ext'd; `iteration += 1` |
| 5 | Send fan-out → 5× worker_node (parallel) | `queen.py:L130` + LangGraph runtime | Each worker receives its `AgentState` dict, validates it, calls role dispatch (`worker.py:L75-L98`), produces `WorkerResult`. **16-LG1 CRITICAL**: returns `{"_worker_result": ..., "_agent_id": ...}` — these keys are NOT on `SwarmState`, with `extra='forbid'` the next `model_validate` raises | (real LangGraph) ValidationError; (mock) manual append works |
| 6 | All workers done → collect_results | `factory.py:L94-L96` | `collect_results_node` reads `swarm.worker_results`, converts each via `to_vote()`, appends to `pending_votes`. **16-LG2**: `swarm.tasks[i].status` not updated | `pending_votes` populated, `status="voting"` |
| 7 | collect_results → consensus_node | `factory.py:L97` | `consensus_node` calls `run_consensus(votes, protocol="raft", ...)`. With queen role absent in pure worker votes (no queen produced output), Raft falls back to `majority_consensus`. **17-CORR1 CRITICAL**: string-equality bucketing — semantically equivalent outputs split votes | `consensus_result` set |
| 8a | consensus → judge_node (low risk) | `consensus.py:L67-L73` cond. edge | `route_after_consensus` returns `"judge_node"` when `requires_approval=False` | routes to judge |
| 8b | consensus → approval_node (high risk) | same | `route_after_consensus` returns `"approval_node"` when `risk_score ≥ 0.8` | (W2 path) |
| 9 | judge_node | `judge.py:L18-L62` | `swarm.check_drift(candidate)` keyword-overlap. **18-CORR1 high**: false positives. If accepted: `final_output = candidate`, `status="distilling"` | `final_output` set |
| 10 | judge → distill_node | `factory.py:L118-L123` | `distill_node` runs DISTILL (remove low-score memory) then CONSOLIDATE (`memory.store(pattern_key, final_output, score=agreement_fraction)`); `increment_sona`, `status="completed"` | `memory.entries` += pattern; `sona_cycle_count += 1` |
| 11 | distill_node → END | `factory.py:L126` | terminate | final SwarmState returned |

## Round-trip check (lossless?)

- `to_json_dict()` uses `model_dump(mode="json")` (`models/base.py:L52`) ✅
- `from_json_dict()` uses `model_validate` (`models/base.py:L57`) ✅
- Every node returns `swarm.to_json_dict()` ✅

**Verified lossless** for all `SwarmState` fields **except**:
- `worker_results` populated via worker `_worker_result` key — does NOT round-trip through `extra='forbid'` (16-LG1 critical bug).
- `_index` private dict on `SwarmMemory` — not serialised explicitly; rebuilt on validate via `_rebuild_index` ✅.

## `objective_hash` survival

| Step | objective_hash check | Verified? |
|---|---|---|
| 0 (construction) | `stable_hash(objective)[:16]` | ✅ `state.py:L107-L112` |
| 4 (queen) | embedded in every `QueenDirective.objective_hash` | ✅ `queen.py:L120` |
| 5 (worker) | available via `agent_state.task_context["objective_hash"]` | ✅ via `directive.model_dump()` |
| 9 (judge) | `swarm.check_drift(candidate)` uses `self.objective` not the hash directly | ⚠️ **partial** — `objective_hash` exists but isn't compared to a fresh hash; the comparison is keyword-overlap |
| 10 (distill) | pattern key embeds `objective_hash` | ✅ `sona.py:L43` |

**Verdict:** the hash is *carried* end-to-end ✅, but it's only *used* for pattern keying, never to detect tampering of the objective field.

## `history` cap (500) and `errors` cap (100) at every write?

| Write site | Cap enforced | File:Line |
|---|---|---|
| `swarm.append_history(kind, payload)` | ✅ | `state.py:L176-L181` (slices to 500) |
| `swarm.add_error(msg)` | ✅ | `state.py:L173-L174` (slices to 100) |
| `swarm.errors = [...]` direct assignment | ✅ via `validate_assignment=True` + `_cap_lists` validator | `state.py:L116-L121` |
| Direct mutation `swarm.history.append(...)` | ❌ **NOT capped** until next assignment | bypass risk |

**Verdict:** caps work for the documented helpers ✅. **But**: any code path that does `swarm.history.append(...)` instead of `swarm.append_history(...)` bypasses the cap until the next assignment to `history` triggers the validator. No such call site exists in current code (verified by grep on `.history.append`), but it's a latent risk. Recommend changing `history: list[dict]` → a custom container with bounded `append`.

## Findings linked to W1
- **16-LG1 (critical)** — worker results don't propagate
- **17-CORR1 (critical)** — string-eq bucketing
- **18-CORR1 (high)** — drift heuristic false-positive rate
- **27-LG1 (high)** — SONA retrieve is no-op
- **14-CORR1 (high)** — every task lands in tier3
- **13-T1 (critical)** — missing reducer for parallel Sends (root cause of 16-LG1)
