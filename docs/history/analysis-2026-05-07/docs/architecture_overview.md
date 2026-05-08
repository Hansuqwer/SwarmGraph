# Architecture Overview — `swarmMain/`

## Three sub-projects, one shared philosophy

```
swarmMain/
├── hive-swarm/                 ← reference framework: Pydantic v2 + LangGraph swarm
├── ai-coder-hardening-improved/ ← applied: hardened LangGraph coding agent
├── ai-provider-swarm-gateway/  ← applied: 9-node provider routing (NOT analysed for compliance)
└── ruflo-swarm-prompt/         ← original Ruflo-inspired research notes
```

All three projects share:

1. **State model** — a single Pydantic `BaseModel` that is `extra='forbid'` + `validate_assignment=True` and JSON-round-tripped on every node boundary.
2. **Graph factory** — a function that builds a `StateGraph(dict)` with conditional edges and a `BaseCheckpointSaver`-derived saver.
3. **Redacting checkpointer** — a wrapper around `BaseCheckpointSaver` that scrubs secrets before write while preserving paths needed for resume.
4. **Anti-drift / objective-hash** — a stable hash of the original objective embedded in state and checked at every judge node.

## `hive-swarm/` — node graph (verified)

```
START
  └─→ memory_retrieve              (SONA RETRIEVE)
        └─→ route_task              (router_node, scores complexity 0..1)
              ├─→ fast_agent        (tier1_fast,  score < 0.15)  ─→ distill_node
              ├─→ medium_agent      (tier2_medium, 0.15 ≤ s < 0.50) ─→ distill_node
              └─→ <topology>_queen  (tier3_swarm, s ≥ 0.50)
                    │   {hierarchical|mesh|ring|star|adaptive}_queen
                    └─Send()─▶ worker_node (×N, parallel)
                                  └─→ collect_results          (fan-in)
                                        └─→ consensus_node     (raft|bft|gossip|majority)
                                              ├─→ approval_node (if risk ≥ 0.8)  ─→ judge_node
                                              ├─→ judge_node    (anti-drift check)
                                              │     ├─→ distill_node              (SONA DISTILL+CONSOLIDATE)
                                              │     │     └─→ END
                                              │     └─→ route_task                (retry, if iter < max)
                                              └─→ END (failed)
```

Verified at `hive-swarm/swarm/graphs/factory.py:L72-L130`.

## `ai-coder-hardening-improved/` — node graph (verified)

```
START
  └─→ plan_node
        └─→ propose_patch_node    (returns (state, PatchOutput))
              └─→ validate_patch_node
                    ├─→ awaiting_approval (if cmd needs approval)
                    │     └─→ interrupt() → run_tests_node
                    └─→ run_tests_node
                          └─→ review_node
                                └─→ END | failed
```

Verified at `ai-coder-hardening-improved/src/ai_coder/workflow/nodes.py:L40-L260`.

## `ai-provider-swarm-gateway/` — 9-node graph (verified)

```
intake → classify → provider_filter → quota_check → swarm_route
       → consensus → provider_call → response_validation → usage_update → END
```

Verified at `ai-provider-swarm-gateway/src/ai_provider_swarm_gateway/graph/nodes.py:L70-L240`.

## Shared idioms across all three

| Idiom | Where | Status |
|---|---|---|
| `model_config = ConfigDict(extra='forbid', validate_assignment=True)` | `HardenedModel`, `WorkflowState`, `GatewayState` | ✅ uniform |
| `model_config = ConfigDict(extra='forbid', frozen=True)` | `FrozenModel`, `MemoLesson`, `SwarmConfig` | ✅ uniform |
| Atomic file writes (`tempfile.mkstemp` + `os.replace`) | `FileCheckpointStore.save`, `LocalCheckpointStore.save` | ✅ uniform |
| `RedactingCheckpointer` wrapping `BaseCheckpointSaver` | `SwarmRedactingCheckpointer`, `RedactingCheckpointer` | ⚠️ duplicated — consolidation candidate |
| `objective_hash` / `prompt_hash` for drift detection | `SwarmState.objective_hash`, `WorkflowState.prompt_hash` | ✅ same pattern |
| `stable_hash(text, length=16)` SHA-256 prefix | `hive-swarm/swarm/models/base.py:L29` | ⚠️ only in hive-swarm; ai-coder uses full SHA-256 |
| Bounded `history` list (cap 500) | `SwarmState`, `WorkflowState` | ✅ uniform |
| Bounded `errors` list (cap 100) | `SwarmState`, `WorkflowState` | ✅ uniform |

## Cross-project consolidation opportunities (preview — full list in `HIVE_ANALYSIS_REPORT.md`)

1. **Single `RedactingCheckpointer`** package shared by all three projects (currently 2 implementations).
2. **Single `stable_hash` / `objective_hash` helper** — currently fork at hash length (16-char prefix vs full).
3. **Single `bounded_list_validator`** Pydantic helper — currently re-implemented 3× as `_cap_lists`.
4. **Single `HistoryEntry` discriminated-union module** — `ai-coder` has it (verified), `hive-swarm` does not.
