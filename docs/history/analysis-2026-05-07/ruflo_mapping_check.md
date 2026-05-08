# Ruflo → Python Mapping Verification

> Verifies every row of the mapping table in `hive-swarm/HIVE_LEADER_SYNTHESIS.md`.
> ✅ = mapping exists and matches; ⚠️ = mapping exists but partial / misnamed; ❌ = mapping claimed but absent.

| # | Ruflo concept | Synthesis claim | Verified? | Evidence |
|---|---|---|---|---|
| 1 | `swarm_init(topology, maxAgents)` | `SwarmConfig + SwarmState` | ✅ | `models/config.py:L11`, `models/state.py:L42` |
| 2 | `agent_spawn(type, name)` | `AgentSpec + state.register_agent()` | ✅ | `models/agent.py:L17`, `models/state.py:L196-L199` |
| 3 | Queen → Workers fan-out | `queen_node() + Send()` | ✅ | `nodes/queen.py:L86, L130` |
| 4 | Hierarchical topology | `_hierarchical_decompose() + Raft` | ✅ | `nodes/queen.py:L21, _DECOMPOSE_FN["hierarchical"]` |
| 5 | Mesh topology | `_mesh_decompose() + Gossip` | ⚠️ | decompose exists (`queen.py:L41`), but **no peer-to-peer** at runtime — see W6/25-CORR1; mesh + gossip is just parallel fan-out + weighted majority |
| 6 | Ring topology | `_ring_decompose() sequential` | ⚠️ | decompose exists (`queen.py:L51`), but **NOT sequential** at runtime — workers run in parallel |
| 7 | Star topology | `_star_decompose() + BFT` | ⚠️ | decompose exists (`queen.py:L65`), no actual hub-spoke isolation |
| 8 | Adaptive topology | "Starts hierarchical, routes" | ❌ | `nodes/queen.py:L80`: `"adaptive": _hierarchical_decompose` — NEVER actually adapts |
| 9 | Raft consensus | `raft_consensus()` | ⚠️ | `models/consensus.py:L48` — implementation is "queen-vote-wins", not full Raft (no terms, no log replication). 21-CORR1. |
| 10 | BFT consensus | `bft_consensus()` (2/3 quorum) | ⚠️ | `models/consensus.py:L88` — math correct for n≥4 but unanimity-required at n=3 (22-C1); votes unsigned (22-SEC1). |
| 11 | Gossip consensus | `gossip_consensus()` (weighted) | ⚠️ | `models/consensus.py:L135` — single-round weighted voting, not multi-round gossip (23-CORR1). |
| 12 | CRDT / Majority | `majority_consensus()` | ⚠️ | `models/consensus.py:L177` — plain majority; no CRDT semantics. Misnomer. |
| 13 | Anti-drift | `state.check_drift() + judge_node()` | ⚠️ | `state.py:L143-L155` + `nodes/judge.py:L40-L48` — keyword-overlap heuristic, high false-positive rate (18-CORR1). |
| 14 | SONA loop | RETRIEVE→JUDGE→DISTILL→CONSOLIDATE→ROUTE | ⚠️ | RETRIEVE (`sona.py:L66`), DISTILL (`sona.py:L31`), CONSOLIDATE (`sona.py:L41`) all present. **But RETRIEVE results are discarded** (27-LG1). The "loop" is single-pass per swarm, not intra-graph. |
| 15 | AgentDB / HNSW | `SwarmMemory + VectorMemoryAdapter` | ⚠️ | `models/memory.py:L52` (memory) + `L168` (adapter). Adapter is a stub: `embed()` returns `[]` ⇒ always falls back to keyword search. No HNSW backend shipped. |
| 16 | EWC++ (no forgetting) | `memory.promote_score()` | ❌ | `memory.py:L141`: `new_score = min(1.0, existing.score + 0.05)`. Plain score bump; no Fisher-information weighting. **Misnamed as EWC++**. (01-DOC2) |
| 17 | Claims (human gate) | `approval_node() + interrupt()` | ⚠️ | `nodes/approval.py:L26-L62` correctly uses `interrupt()`. **But no single-use guard / fingerprint / expiry** — vs ai-coder's `approval_consumed + approval_command_fingerprint`. (19-SEC1) |
| 18 | 3-Tier routing | `route_task()` conditional edge | ✅ | `nodes/router.py:L82-L92` + `factory.py:L82-L88`. Heuristic biases nearly everything to tier 3 (14-CORR1) but the routing mechanism itself is correct. |
| 19 | Post-task checkpoints | `InProcessCheckpointStore / FileCheckpointStore` | ✅ | `nodes/checkpointing.py:L26 (in-process), L73 (file with atomic write)`. No Postgres backend (claimed in some docs, missing). |
| 20 | Secret redaction | `SwarmRedactingCheckpointer` | ⚠️ | `nodes/checkpointing.py:L98` — covers all 8 BaseCheckpointSaver methods ✅, but the redaction regex is toy (`obj.startswith("sk-")` only). 20-SEC1 critical. |

## Summary

- ✅ **5/20 fully verified** — `swarm_init`, `agent_spawn`, queen-Send, hierarchical, 3-tier routing.
- ⚠️ **13/20 partially verified** — exist but with one or more behavioural / nomenclature gaps.
- ❌ **2/20 misclaimed** — adaptive topology, EWC++ (both flagged in `agent_01_mission_drift.md`).

## Recommendation

Update `HIVE_LEADER_SYNTHESIS.md` to:
1. Demote "✅ COMPLETED" → "✅ Scaffolding complete; runtime semantics for mesh/ring/star/adaptive pending; consensus protocols are LLM-adapted simplifications".
2. Replace "EWC++" → "score-promotion (EWC-inspired)".
3. Add a "Known Limitations" section listing the 13 partial mappings with links to fixes.
