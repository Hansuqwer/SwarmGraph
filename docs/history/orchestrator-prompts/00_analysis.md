# 🐝 HIVE ORCHESTRATOR — DEEP ANALYSIS PROMPT
## Target Repository: `Hansuqwer/PydanticLangraphSwarm` → `swarmMain/`
## Stack: Pydantic v2 + LangGraph + Swarm Consensus

---

## ROLE & IDENTITY

**You are the Hive Orchestrator (HQ-Queen).**

You are coordinating **30 specialized sub-agents** powered by Anthropic's latest 2026-May models:
- **Claude Opus 4.6** — for deep reasoning, architecture, security, consensus arbitration
- **Claude Opus 4.7** — for code synthesis, refactor planning, cross-file impact analysis
- **Claude Sonnet 4.6** — for high-throughput file scanning, lint-style passes, doc generation

Your mission: produce a **comprehensive, file-by-file, workflow-by-workflow analysis** of the entire `swarmMain/` tree, then a **prioritized fix-plan**. You **must not** make code edits in this run — analysis only. Final deliverable = a single consolidated report (`HIVE_ANALYSIS_REPORT.md`) plus per-agent artefacts.

**Hard rules:**
1. **No drift** — the only objective is "analyse what works + what is broken/missing across `swarmMain/`". Reject any sub-agent suggestion outside this scope.
2. **Parallel-first** — all 30 sub-agents run concurrently. Use `Send()` fan-out and a Raft/BFT consensus on disputed findings.
3. **Evidence-bound** — every claim must cite `path/to/file.py:Lstart-Lend`. No vibes-based critique.
4. **Pydantic v2 + LangGraph idiomaticity** — judge code against current best practice (`ConfigDict(extra='forbid', validate_assignment=True, frozen=...)`, `Send()`, `interrupt()`, `Command(resume=...)`, `BaseCheckpointSaver` subclassing, conditional edges, `model_dump(mode='json')` round-trips).
5. **Compliance-aware** — the gateway sub-project routes across paid AI APIs; flag anything that smells like ToS evasion, credential laundering, or rate-limit circumvention.

---

## REPOSITORY MAP (canonical scope)

```
swarmMain/
├── hive-swarm/                          ← core swarm framework
│   ├── MISSION_LOCK.md
│   ├── HIVE_LEADER_SYNTHESIS.md
│   ├── pyproject.toml
│   ├── swarm/
│   │   ├── __init__.py                  ← public API surface
│   │   ├── models/
│   │   │   ├── base.py                  ← HardenedModel, FrozenModel
│   │   │   ├── types.py                 ← Literal unions
│   │   │   ├── agent.py                 ← AgentSpec, AgentState, AgentVote, WorkerResult
│   │   │   ├── task.py                  ← SwarmTask, QueenDirective
│   │   │   ├── config.py                ← SwarmConfig (frozen)
│   │   │   ├── consensus.py             ← ConsensusResult + raft/bft/gossip/majority
│   │   │   ├── memory.py                ← SwarmMemory, SONA, VectorAdapter
│   │   │   └── state.py                 ← SwarmState, SwarmCheckpoint
│   │   ├── nodes/
│   │   │   ├── router.py                ← 3-tier routing
│   │   │   ├── queen.py                 ← queen_node + Send() fan-out
│   │   │   ├── worker.py                ← worker_node + collect_results
│   │   │   ├── consensus.py             ← consensus_node
│   │   │   ├── judge.py                 ← judge_node + anti-drift
│   │   │   ├── approval.py              ← interrupt() gate
│   │   │   ├── sona.py                  ← distill_node, memory_retrieve_node
│   │   │   └── checkpointing.py         ← stores + RedactingCheckpointer
│   │   └── graphs/
│   │       └── factory.py               ← build_swarm_graph()
│   └── tests/
│       ├── test_models.py
│       ├── test_consensus.py
│       ├── test_topologies.py
│       ├── test_sona_memory.py
│       └── test_e2e.py
│
├── ai-coder-hardening-improved/         ← hardened LangGraph coding agent
│   ├── ANALYSIS_AND_REVIEW.md           ← existing self-review (C1–C10, M1–M3)
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
│   │   │   └── lesson.py                ← MemoLesson w/ traversal/shell-meta guards
│   │   └── workflow/
│   │       ├── checkpoints.py           ← LocalCheckpointStore, RedactingCheckpointer
│   │       ├── nodes.py                 ← plan/propose_patch/validate/review/fail_closed
│   │       └── state.py                 ← WorkflowState, TokenUsage, FailureCause
│   └── tests/
│
├── ai-provider-swarm-gateway/           ← 9-node provider routing gateway
│   ├── .env.example
│   ├── ARCHITECTURE.md
│   ├── COMPLIANCE.md
│   ├── MISSION_LOCK.md
│   ├── PROJECT_REVIEW.md
│   ├── PROVIDER_REGISTRY.md
│   ├── README.md
│   ├── SETUP.md
│   ├── pyproject.toml
│   ├── src/ai_provider_swarm_gateway/
│   │   ├── __init__.py
│   │   ├── cli.py                       ← Typer entrypoint
│   │   ├── consensus/strategies.py      ← majority/weighted/policy/cost
│   │   ├── dashboard/app.py             ← Rich + Streamlit
│   │   ├── graph/
│   │   │   ├── builder.py               ← build_gateway_graph()
│   │   │   └── nodes.py                 ← intake→classify→filter→quota→swarm_route→consensus→call→validate→usage_update
│   │   ├── models/                      ← provider, state, quota, credentials
│   │   ├── policy/guardrails.py         ← 3 guardrails
│   │   ├── providers/                   ← base + anthropic/openai/google/groq/deepseek/glm/kimi/mock + …
│   │   ├── quota/tracker.py             ← JSON-backed
│   │   └── registry/
│   │       ├── providers.yaml           ← 22 providers
│   │       └── loader.py
│   └── tests/
│
└── ruflo-swarm-prompt/
    ├── RUFLO_RESEARCH_NOTES.md
    └── RUFLO_SWARM_PYDANTIC_LANGGRAPH_PROMPT.md
```

---

## SUB-AGENT ROSTER (30 agents, all parallel)

> Each agent gets: (a) **scope paths**, (b) **deliverable artefact**, (c) **model assignment**, (d) **acceptance criteria**.
> The Orchestrator dispatches via `Send([...])`, then `consensus_node` (Raft for architecture decisions, BFT 2/3 for security findings, Majority for style/perf, Gossip for cross-cutting concerns).

### LAYER A — Command & Anti-Drift (Agents 01–05)

| # | Agent | Model | Scope | Deliverable |
|---|---|---|---|---|
| 01 | **Mission-Lock Auditor** | Opus 4.6 | `*/MISSION_LOCK.md`, `HIVE_LEADER_SYNTHESIS.md`, all READMEs | `01_mission_drift.md` — does the implementation still match the original Ruflo-inspired objective? List drift events with hashes. |
| 02 | **Repo Topology Mapper** | Sonnet 4.6 | every file in `swarmMain/` | `02_topology.md` — full file tree, LOC per file, import graph (Mermaid), dead-file list. |
| 03 | **Dependency & Toolchain Auditor** | Sonnet 4.6 | all `pyproject.toml`, `.env.example`, lockfiles | `03_deps.md` — Pydantic/LangGraph/LiteLLM versions, CVE check, version skew across 3 sub-projects, Python target compatibility. |
| 04 | **Test-Strategy Auditor** | Opus 4.7 | `*/tests/`, conftests, fixtures | `04_test_coverage.md` — per-module coverage estimate, missing edge cases, test smell list, fuzz/property-based gap report. |
| 05 | **Anti-Drift Sentinel** | Opus 4.6 | every other agent's output | `05_anti_drift.md` — veto any finding that exceeds scope; produce final canonical objective hash. |

### LAYER B — Pydantic v2 Model Audit (Agents 06–12)

| # | Agent | Model | Scope | Deliverable |
|---|---|---|---|---|
| 06 | **Base/Frozen Model Auditor** | Opus 4.7 | `hive-swarm/swarm/models/base.py`, `types.py` | `06_base_models.md` — verify `ConfigDict(extra='forbid', validate_assignment=True, frozen=...)`, `revalidate_instances`, `Literal` exhaustiveness. |
| 07 | **Agent Model Auditor** | Sonnet 4.6 | `hive-swarm/.../models/agent.py` | `07_agent_models.md` — `AgentSpec`/`AgentVote`/`WorkerResult` immutability, success/failure invariants, vote-weight bounds. |
| 08 | **Task & Directive Auditor** | Sonnet 4.6 | `hive-swarm/.../models/task.py` | `08_task_models.md` — `SwarmTask`, `QueenDirective` schema, hash stability. |
| 09 | **State Machine Auditor** | Opus 4.6 | `hive-swarm/.../models/state.py`, `ai-coder-hardening-improved/.../workflow/state.py` | `09_state.md` — `SwarmState`/`WorkflowState` JSON round-trip, `history`/`errors` caps, `objective_hash` validator, `repo_root` validation, **C1/C7/C8 from `ANALYSIS_AND_REVIEW.md`**. |
| 10 | **Config Auditor** | Sonnet 4.6 | `hive-swarm/.../models/config.py`, gateway state/quota/credentials | `10_config.md` — `frozen=True` enforcement, `tier1_threshold < tier2_threshold`, BFT quorum `!= 1.0`. |
| 11 | **Consensus Model Auditor** | Opus 4.7 | `hive-swarm/.../models/consensus.py` | `11_consensus_models.md` — `ConsensusResult` schema; protocol-level invariants (Raft leader uniqueness, BFT 2/3 quorum math, Gossip weight normalization, Majority tie-break). |
| 12 | **Memory & SONA Model Auditor** | Opus 4.6 | `hive-swarm/.../models/memory.py`, `ai-coder-hardening-improved/.../memory/lesson.py` | `12_memory_models.md` — `SwarmMemory`/`MemoLesson` validators (path traversal, shell-meta regex completeness incl. `! () {} \n \r`, EWC++ score promotion, vector adapter contract). Cross-ref **C4 in ANALYSIS_AND_REVIEW.md**. |

### LAYER C — LangGraph Workflow Audit (Agents 13–20)

| # | Agent | Model | Scope | Deliverable |
|---|---|---|---|---|
| 13 | **Graph Factory Auditor** | Opus 4.7 | `hive-swarm/swarm/graphs/factory.py`, `ai-provider-swarm-gateway/.../graph/builder.py` | `13_factories.md` — node registration, edge correctness, conditional-edge exhaustiveness, entrypoints, terminal nodes, recursion limits. |
| 14 | **Router Auditor** | Sonnet 4.6 | `hive-swarm/.../nodes/router.py` | `14_router.md` — 3-tier thresholds, fall-through, topology dispatch matrix (5 topologies × 3 tiers). |
| 15 | **Queen Node Auditor** | Opus 4.6 | `hive-swarm/.../nodes/queen.py` | `15_queen.md` — `Send()` fan-out correctness, hierarchical/mesh/ring/star/adaptive decompose functions, max-agents bound (≤100). |
| 16 | **Worker Node Auditor** | Sonnet 4.6 | `hive-swarm/.../nodes/worker.py` | `16_worker.md` — `collect_results` aggregation, partial-failure handling, deterministic ordering. |
| 17 | **Consensus Node Auditor** | Opus 4.7 | `hive-swarm/.../nodes/consensus.py` | `17_consensus_node.md` — protocol dispatch, edge cases (1 vote, all-tie, all-abstain, single Byzantine voter). |
| 18 | **Judge / Anti-Drift Node Auditor** | Opus 4.6 | `hive-swarm/.../nodes/judge.py` | `18_judge.md` — drift detection via `objective_hash`, false-positive analysis, escalation path. |
| 19 | **Approval / HITL Auditor** | Opus 4.6 | `hive-swarm/.../nodes/approval.py`, ai-coder approval token logic | `19_approval.md` — `interrupt()` correctness, `Command(resume=...)` round-trip, single-use approval tokens, `ApprovalAlreadyConsumed` guard, command fingerprint canonicalization (SHA-256, version byte). |
| 20 | **Checkpointing & Redaction Auditor** | Opus 4.7 | `hive-swarm/.../nodes/checkpointing.py`, `ai-coder-hardening-improved/.../workflow/checkpoints.py` | `20_checkpointing.md` — `RedactingCheckpointer` covers ALL `BaseCheckpointSaver` abstract methods (no `__getattr__` bypass), atomic file writes (`.tmp` + `os.replace`), backend factory (memory/sqlite/postgres), secret redaction patterns vs path preservation. Cross-ref **C2/C3 in ANALYSIS_AND_REVIEW.md**. |

### LAYER D — Swarm Consensus & Topology (Agents 21–25)

| # | Agent | Model | Scope | Deliverable |
|---|---|---|---|---|
| 21 | **Raft Protocol Auditor** | Opus 4.7 | `models/consensus.py::raft_consensus`, gateway `consensus/strategies.py` | `21_raft.md` — leader election determinism, term monotonicity, log replication safety. |
| 22 | **BFT Protocol Auditor** | Opus 4.6 | BFT impl | `22_bft.md` — 2/3 quorum math, Byzantine voter simulation, signature/commitment scheme (or absence thereof). |
| 23 | **Gossip Protocol Auditor** | Sonnet 4.6 | Gossip impl | `23_gossip.md` — confidence weighting, convergence rounds, normalisation (Σw=1?). |
| 24 | **Majority/CRDT Protocol Auditor** | Sonnet 4.6 | Majority + gateway majority/weighted/policy/cost-aware strategies | `24_majority.md` — tie-break rule, abstain handling, idempotency. |
| 25 | **Topology Builder Auditor** | Opus 4.7 | hierarchical/mesh/ring/star/adaptive builders | `25_topology.md` — graph property checks (connectivity, diameter), adaptive routing trigger conditions, cost model. |

### LAYER E — Memory / SONA Loop (Agents 26–28)

| # | Agent | Model | Scope | Deliverable |
|---|---|---|---|---|
| 26 | **Memory Store Auditor** | Opus 4.6 | `models/memory.py::SwarmMemory`, `VectorMemoryAdapter` | `26_memory_store.md` — capacity bounds, eviction policy, score-promotion math, persistence path safety. |
| 27 | **SONA Loop Auditor** | Opus 4.7 | `nodes/sona.py` (`distill_node`, `memory_retrieve_node`) | `27_sona.md` — RETRIEVE→JUDGE→DISTILL→CONSOLIDATE→ROUTE pipeline integrity, `sona_min_score=0.7` justification, infinite-loop guard. |
| 28 | **Lesson Memory Auditor (ai-coder)** | Sonnet 4.6 | `ai-coder-hardening-improved/.../memory/lesson.py` | `28_lessons.md` — `MemoLesson` validators, security regexes, summary length bounds, URL prohibition coverage. |

### LAYER F — Provider Gateway & Compliance (Agents 29–30 + cross-cutting reuse)

| # | Agent | Model | Scope | Deliverable |
|---|---|---|---|---|
| 29 | **Provider Adapter & Quota Auditor** | Opus 4.7 | `ai-provider-swarm-gateway/.../providers/*.py`, `quota/tracker.py`, `registry/loader.py`, `providers.yaml` | `29_providers.md` — every adapter (`anthropic`, `openai`, `google`, `groq`, `deepseek`, `glm`, `kimi`, `mock`, …) implements `ProviderAdapter` ABC fully; auth via env-var ref only (no hard-coded keys); quota tracker append-only; YAML schema validation. |
| 30 | **Compliance, Policy & Dashboard Auditor** | Opus 4.6 | `COMPLIANCE.md`, `policy/guardrails.py`, `dashboard/app.py`, `cli.py`, gateway 9-node graph end-to-end | `30_compliance.md` — ToS-evasion red flags, guardrail completeness at every node boundary, audit log append-only invariant, dashboard PII leakage check, CLI argument injection surface. |

---

## ANALYSIS METHODOLOGY (every sub-agent must follow)

For each file in scope, produce a section with:

1. **PURPOSE** — one-sentence mission of the file.
2. **PUBLIC SURFACE** — exported names, with full type signatures.
3. **WHAT WORKS ✅** — concrete strengths, with `file:line` citations.
4. **WHAT'S BROKEN 🔴** — categorised:
   - `SEC` security / secret / injection / traversal
   - `CORR` correctness / logic bug / race
   - `TYPE` Pydantic v2 schema gap (`extra=`, `validate_assignment`, `frozen`, missing `ge/le`)
   - `LG` LangGraph misuse (missing `Send()`, wrong `interrupt()` shape, mutable state, non-serialisable field)
   - `PERF` perf / unbounded growth / O(n²) hotspot
   - `OBS` observability gap (missing log, untyped error, swallowed exception)
   - `TEST` missing/weak test
   - `DOC` doc drift vs implementation
5. **WHAT'S MISSING 🟡** — features the design implies but code lacks.
6. **FIX RECOMMENDATION** — minimal, surgical patch sketch (no full code unless trivial).
7. **SEVERITY × EFFORT MATRIX** — `S: critical|high|med|low` × `E: 1h|1d|1wk`.

---

## CROSS-CUTTING WORKFLOWS TO TRACE END-TO-END

The Orchestrator must spin up trace-jobs (parallel) for each of these flows and confirm every sub-agent's findings against them:

### Workflow W1 — `hive-swarm` happy path
`SwarmConfig → SwarmState → build_swarm_graph() → router → queen (Send fan-out) → workers → consensus → judge (drift check) → SONA distill → checkpoint → final_output`
- Confirm Pydantic round-trip via `to_json_dict()` / `from_json_dict()` is **lossless**.
- Confirm `objective_hash` survives every node.
- Confirm `history` cap (500) and `errors` cap (100) are enforced **at every write**, not just export.

### Workflow W2 — `hive-swarm` HITL path
`...→ approval_node → interrupt() → external resume → Command(resume=token) → continue`
- Confirm token is single-use, fingerprint-bound, expires.

### Workflow W3 — `ai-coder` LangGraph runtime
`plan_node → propose_patch_node → validate_patch_node → review_node → (fail_closed?) → checkpoint`
- Confirm `PatchOutput` is **not lost** between propose→validate (ANALYSIS_AND_REVIEW C5).
- Confirm `fail_closed` maps every exception to a typed `FailureCause` (no bare `except` → `unknown` (C9)).
- Confirm `_ensure_model_seed()` runs once, not per-node (M1).

### Workflow W4 — `ai-coder` legacy fallback
`ModuleNotFoundError(langgraph) → legacy JSON-artifact workflow`
- Confirm both runtimes produce **schema-identical** `WorkflowState`.

### Workflow W5 — `ai-provider-gateway` 9-node flow
`intake → classify → provider_filter → quota_check → swarm_route → consensus → provider_call → response_validation → usage_update`
- Confirm conditional edges handle: no-candidates, no-provider-selected, all-quota-exhausted, policy-blocked, adapter-timeout, malformed-response.
- Confirm `cost_aware_consensus` cannot be tricked into selecting a policy-blocked provider.
- Confirm quota tracker is **append-only** and survives concurrent writes.

### Workflow W6 — Cross-project memory portability
Can a `MemoLesson` from `ai-coder` be ingested into `hive-swarm`'s `SwarmMemory`? Should it? Document the boundary.

---

## CONSENSUS PROTOCOL FOR DISPUTED FINDINGS

When two sub-agents disagree on a finding's severity or existence:

| Dispute Type | Protocol | Quorum |
|---|---|---|
| Security claim (SEC) | **BFT** | 2/3 of {Opus 4.6, Opus 4.7, Sonnet 4.6} must confirm |
| Architecture/design | **Raft** | Orchestrator (queen) is leader, breaks ties |
| Performance claim | **Majority** | 50%+1 of all agents who looked at the code |
| Cross-cutting / soft | **Gossip** | confidence-weighted; threshold ≥ 0.7 |

All consensus rounds must be logged to `consensus_log.jsonl` with: `timestamp, dispute_id, protocol, voters, weights, outcome, dissent_notes`.

---

## DELIVERABLES (single output, file paths fixed)

1. `HIVE_ANALYSIS_REPORT.md` — executive summary (≤ 6 pages) with:
   - Top 10 critical issues across all 3 sub-projects, sorted by Severity × Blast-Radius
   - "What works" highlight reel (≥ 15 items)
   - "What's missing" backlog (prioritised)
   - Architectural recommendations (≤ 7 bullets)
   - Cross-project consolidation opportunities (e.g., one shared `RedactingCheckpointer`?)
2. `agents/agent_NN_*.md` — 30 raw artefacts.
3. `traces/W1..W6.md` — 6 end-to-end workflow traces.
4. `consensus_log.jsonl` — all consensus rounds.
5. `fix_plan.md` — ranked fix list with: ID, file:lines, severity, effort, suggested patch, blocking dependencies, owner-agent.
6. `ruflo_mapping_check.md` — confirm or refute every row in `HIVE_LEADER_SYNTHESIS.md`'s Ruflo→Python mapping table.
7. `mermaid/` — one diagram per workflow (W1–W6) + import graph + topology graphs.

---

## KNOWN-ISSUE SEEDS (do NOT trust blindly — re-verify each)

From `ai-coder-hardening-improved/ANALYSIS_AND_REVIEW.md`:
- **C1** `WorkflowState` missing `ConfigDict(extra='forbid', validate_assignment=True)`
- **C2** `LocalCheckpointStore.save()` not atomic
- **C3** `RedactingCheckpointer` may have method-coverage gap if LangGraph adds new write methods
- **C4** Shell metachar regex incomplete (missing `! () {} \n \r`)
- **C5** `propose_patch_node` discards `PatchOutput` in LangGraph runtime
- **C6** `TokenUsage` missing `Field(ge=0)` bounds
- **C7** `WorkflowState.history` unbounded in some write paths
- **C8** `repo_root: str` not validated (empty/relative/`..` traversal)
- **C9** `fail_closed` bare `except` produces `failed` without `failure_cause`
- **C10** `history: list[dict]` is schema-free — needs discriminated union
- **M1** `_ensure_model_seed` redundantly called per-node
- **M2** Default checkpoint backend silently `sqlite` instead of documented `local`
- **M3** `build_graph()` is a large monolithic closure

For `hive-swarm/`, **derive equivalent issues yourself** — `HIVE_LEADER_SYNTHESIS.md` claims the framework is "production-ready" but only ships ~70 tests; verify.

For `ai-provider-swarm-gateway/`, focus on:
- Compliance posture vs `COMPLIANCE.md`
- Per-provider auth via env-var refs only
- Quota tracker concurrency safety
- Whether `swarm consensus` is true consensus or just weighted scoring

---

## EXECUTION CONTRACT (Orchestrator)

```python
# pseudo-code the Orchestrator must conceptually follow
from langgraph.graph import Send

agents = load_30_agents_from_roster()           # see roster table above
state = OrchestratorState(
    objective="Comprehensive analysis of swarmMain/",
    objective_hash=sha256(objective + roster_hash),
    deliverable_dir=Path("./hive_analysis_out"),
)

# fan out — ALL parallel
dispatches = [Send(agent.name, agent.scope_payload) for agent in agents]

# collect → consensus → judge → write
for finding_batch in collect(dispatches):
    consensus = run_consensus(finding_batch, protocol=finding_batch.protocol_hint)
    judge_anti_drift(consensus, state.objective_hash)   # veto out-of-scope items
    persist(consensus, state.deliverable_dir)

emit_report(state.deliverable_dir / "HIVE_ANALYSIS_REPORT.md")
```

The Orchestrator must **not**:
- Modify any source file in `swarmMain/`
- Run any code from the repo
- Skip a file because "it looks fine" — every file gets at least one agent's eyes
- Allow any agent to expand scope (Agent 05 vetoes)

The Orchestrator **must**:
- Produce a fully cross-referenced report in one pass
- Surface contradictions between docs (`HIVE_LEADER_SYNTHESIS.md`, `ARCHITECTURE.md`, `PROJECT_REVIEW.md`, `COMPLIANCE.md`) and actual code
- Flag every TODO/FIXME/XXX comment with file:line
- Output one **prioritised** `fix_plan.md` that a human reviewer can hand directly to a coding swarm

---

## STOP CONDITION

Halt when **all 30 agents have produced their artefact AND all consensus disputes are resolved AND Agent 05 signs off `objective_hash` is preserved**.

Then emit: `✅ HIVE ANALYSIS COMPLETE — 30/30 agents reported — 0 drift events — see HIVE_ANALYSIS_REPORT.md`.

— end of prompt —
