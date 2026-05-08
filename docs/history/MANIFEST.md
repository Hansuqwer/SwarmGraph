# Manifest — `hive_analysis_project/`

> Every file produced by this analysis run, with role and approximate size.

## Root
| File | Role | Size (approx) |
|---|---|---|
| README.md | entry point + folder map | ~3 KB |
| HIVE_ANALYSIS_REPORT.md | ★ executive summary | ~9 KB |
| fix_plan.md | prioritised, owner-tagged fix backlog (73 items) | ~14 KB |
| ruflo_mapping_check.md | Ruflo→Python verification (20 rows) | ~5 KB |
| consensus_log.jsonl | 7 disputed-finding consensus rounds | ~3 KB |
| MANIFEST.md | this file | ~2 KB |
| create_zip.py | zip the whole folder | ~1 KB |

## research/  (May-2026 baseline)
| File | Role |
|---|---|
| 2026_models_baseline.md | Anthropic model lineup as of 7 May 2026 |
| pydantic_v2_best_practices.md | TYPE finding anchor |
| langgraph_best_practices.md | LG finding anchor |
| consensus_protocols_2026.md | CORR finding anchor (Raft/PBFT/Gossip/Majority + LLM-specific) |

## docs/
| File | Role |
|---|---|
| architecture_overview.md | system + 3 sub-projects + cross-cutting patterns |
| methodology.md | 7-section template + finding-ID convention |
| orchestrator_contract.md | hard rules + deliverables contract |

## agents/  (30 sub-agent artefacts)
| File | Layer | Model |
|---|---|---|
| agent_01_mission_drift.md | A — Command | Opus 4.6 |
| agent_02_topology.md | A | Sonnet 4.6 |
| agent_03_deps.md | A | Sonnet 4.6 |
| agent_04_test_coverage.md | A | Opus 4.7 |
| agent_05_anti_drift.md | A | Opus 4.6 |
| agent_06_base_models.md | B — Pydantic | Opus 4.7 |
| agent_07_agent_models.md | B | Sonnet 4.6 |
| agent_08_task_models.md | B | Sonnet 4.6 |
| agent_09_state.md | B | Opus 4.6 |
| agent_10_config.md | B | Sonnet 4.6 |
| agent_11_consensus_models.md | B | Opus 4.7 |
| agent_12_memory_models.md | B | Opus 4.6 |
| agent_13_factories.md | C — LangGraph | Opus 4.7 |
| agent_14_router.md | C | Sonnet 4.6 |
| agent_15_queen.md | C | Opus 4.6 |
| agent_16_worker.md | C | Sonnet 4.6 |
| agent_17_consensus_node.md | C | Opus 4.7 |
| agent_18_judge.md | C | Opus 4.6 |
| agent_19_approval.md | C | Opus 4.6 |
| agent_20_checkpointing.md | C | Opus 4.7 |
| agent_21_raft.md | D — Consensus | Opus 4.7 |
| agent_22_bft.md | D | Opus 4.6 |
| agent_23_gossip.md | D | Sonnet 4.6 |
| agent_24_majority.md | D | Sonnet 4.6 |
| agent_25_topology.md | D | Opus 4.7 |
| agent_26_memory_store.md | E — Memory/SONA | Opus 4.6 |
| agent_27_sona.md | E | Opus 4.7 |
| agent_28_lessons.md | E | Sonnet 4.6 |
| agent_29_providers.md | F — Provider | Opus 4.7 |
| agent_30_dashboard_cli.md | F (re-scoped, no compliance) | Opus 4.6 |

## traces/  (6 end-to-end workflow traces)
| File | Workflow |
|---|---|
| W1_hive_happy_path.md | hive-swarm tier-3 happy path |
| W2_hive_hitl.md | hive-swarm HITL path with `interrupt()` + `Command(resume=...)` |
| W3_aicoder_langgraph.md | ai-coder LangGraph runtime + C/M-series verification |
| W4_aicoder_legacy.md | ai-coder JSON-artefact fallback (partial; re-fetch needed) |
| W5_gateway_9node.md | ai-provider-gateway 9-node flow (partial; re-fetch needed) |
| W6_cross_project_memory.md | MemoLesson ↔ SwarmMemoryEntry portability |

## mermaid/
| File | Diagrams |
|---|---|
| import_graph.md | hive-swarm internal import DAG |
| topology_5x.md | 5 topologies — INTENT vs REALITY pairs |
| workflows_W1_W6.md | one diagram per W1–W6 |

## tests/
| File | Role |
|---|---|
| analysis_assertions.md | 20 machine-checkable claims with grep recipes |

---

## Statistics

- **30** agent artefacts
- **6** workflow traces
- **3** Mermaid documents (~13 diagrams total)
- **4** research documents
- **3** docs files
- **1** test-assertion file
- **7** consensus-log entries
- **1** root README, **1** main report, **1** fix plan, **1** Ruflo mapping check, **1** manifest, **1** zip script
- **Total files:** 50
- **Total written content:** ~120 KB markdown
- **Findings cross-referenced:** 100+ (every finding has an ID like `09-CORR3`, every fix has an ID like `F-29A`)
- **All claims cited** to `path/to/file.py:Lstart-Lend`

---

## How to consume

| Audience | Read order |
|---|---|
| Engineering manager (10 min) | `README.md` → `HIVE_ANALYSIS_REPORT.md` |
| Lead engineer (45 min) | + `fix_plan.md` → `traces/W1.md` → `traces/W3.md` → `traces/W5.md` |
| Security reviewer (90 min) | + agents 19, 20, 22, 28, 29 + `consensus_log.jsonl` |
| Pydantic/LangGraph specialist (90 min) | + agents 06–13 + `research/pydantic_v2_best_practices.md` + `research/langgraph_best_practices.md` |
| Full audit (~4 h) | every file in this folder |
