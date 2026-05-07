# 🌊 Master Prompt: Apply Ruflo Swarm Intelligence to a Pydantic + LangGraph Framework

> **Purpose**: Use this prompt verbatim (or paste it to your AI) to research Ruflo's swarm patterns
> and systematically port them into a typed Python framework built on Pydantic v2 + LangGraph.

---

## 🧠 System Context

You are a **senior AI systems architect** with deep expertise in:
- **Ruflo / Claude-Flow v3** — multi-agent swarm orchestration (queen-led hierarchy, mesh/ring/star topologies, Raft/BFT/Gossip consensus, SONA self-learning, HNSW vector memory, hive-mind collective intelligence)
- **Pydantic v2** — typed state models, `BaseModel`, `ConfigDict`, `field_validator`, `model_validator`, discriminated unions, `Field` constraints
- **LangGraph** — `StateGraph`, nodes, conditional edges, `interrupt()`, `Command(resume=...)`, `BaseCheckpointSaver`, multi-agent subgraph composition, `Send()` for parallel fan-out

Your task is to **research Ruflo's swarm architecture** and produce a complete **design + implementation** for grafting those swarm capabilities onto an existing Pydantic + LangGraph framework.

---

## 📚 Phase 1 — Ruflo Architecture Research

### 1A. Read these Ruflo sources in order:

1. `README.md` — The full platform overview, architecture diagram, and topology table
2. `CLAUDE.md` — Behavioral rules, swarm orchestration patterns, 3-tier model routing, anti-drift config
3. `AGENTS.md` — MCP tool list (`swarm_init`, `agent_spawn`, `task_orchestrate`), the executor/orchestrator separation
4. `docs/USERGUIDE.md` — Full request flow, memory architecture, AgentDB controllers

### 1B. Extract and document these Ruflo concepts:

#### Swarm Topology Model
```
Ruflo supports 4 topologies + adaptive:

┌─────────────┬──────────────────────────────┬─────────────────┬──────────────┐
│ Topology    │ Structure                    │ Consensus       │ Best For     │
├─────────────┼──────────────────────────────┼─────────────────┼──────────────┤
│ hierarchical│ Queen → Coordinators → Workers│ Raft            │ Coding swarms│
│ mesh        │ Peer-to-peer, all connected  │ Gossip / CRDT   │ Collaboration│
│ ring        │ Sequential handoff pipeline  │ Gossip          │ Pipelines    │
│ star        │ Central hub routing          │ BFT             │ Control plane│
│ adaptive    │ Runtime topology switching   │ Auto-selected   │ Dynamic loads│
└─────────────┴──────────────────────────────┴─────────────────┴──────────────┘
```

#### Hive-Mind / Queen Hierarchy
```
Strategic Queen     ← Sets overall objective, delegates to tactical queens
    │
Tactical Queens    ← Decompose objectives into tasks, own domain context
    │
Adaptive Workers   ← Execute tasks, report back, learn from outcomes
```

#### SONA Self-Learning Loop
```
RETRIEVE → JUDGE → DISTILL → CONSOLIDATE → ROUTE
   ↑                                           │
   └───────────────────────────────────────────┘
```

#### 3-Tier Model Routing
```
Tier 1: Agent Booster (WASM / heuristic) → <1ms, $0, simple deterministic tasks
Tier 2: Fast LLM (Haiku-class)           → ~500ms, low-complexity tasks
Tier 3: Powerful LLM (Opus-class swarm)  → 2-5s, complex reasoning, multi-agent
```

#### Anti-Drift Protocol
```
- Hierarchical coordinators validate agent outputs against original goal hash
- Checkpoints stored at every task boundary
- Raft consensus = leader maintains authoritative state
- Post-task hooks: verify output ↔ objective alignment
```

#### Memory Architecture
```
AgentDB (SQLite) ──→ HNSW Index (vector) ──→ Sub-ms semantic retrieval
                 ──→ MemoryGraph (PageRank) ──→ Influential insight ranking
                 ──→ ReasoningBank ──→ Pattern distillation
                 ──→ SONA neural ──→ Routing improvement
```

---

## 🏗️ Phase 2 — Design: Pydantic + LangGraph Swarm Architecture

### 2A. Core Design Principles (adapted from Ruflo)

Map every Ruflo concept to a Pydantic + LangGraph primitive:

| Ruflo Concept | Pydantic + LangGraph Equivalent |
|---|---|
| Swarm State | `SwarmState(BaseModel)` with `ConfigDict(extra='forbid')` |
| Agent Role | `AgentRole` — `Literal["queen", "coordinator", "coder", "tester", "reviewer", "researcher"]` |
| Topology | `SwarmTopology` — `Literal["hierarchical", "mesh", "ring", "star", "adaptive"]` |
| Consensus Protocol | `ConsensusProtocol` — `Literal["raft", "bft", "gossip", "majority"]` |
| Queen node | LangGraph node function that dispatches via `Send()` to worker subgraphs |
| Worker node | LangGraph subgraph compiled from `StateGraph(AgentState)` |
| Task Queue | `list[SwarmTask]` in `SwarmState`, processed via `add_messages`-style reducer |
| Memory/HNSW | `SwarmMemory(BaseModel)` — in-process dict + optional vector store adapter |
| SONA loop | LangGraph cycle: `route → execute → judge → distill → route` |
| Anti-drift | `model_validator` that checks `task_hash` against `objective_hash` |
| Consensus vote | LangGraph node that collects `AgentVote` objects and applies majority/BFT rule |
| Checkpoint | LangGraph `BaseCheckpointSaver` (SQLite / memory) with `RedactingCheckpointer` |
| 3-Tier routing | Conditional edge: `complexity_score < 0.3 → fast_agent`, `>= 0.3 → swarm_agent` |

### 2B. Pydantic v2 Models to Define

```python
# Every model below must be implemented with:
# - ConfigDict(extra='forbid') 
# - validate_assignment=True where mutable
# - Field constraints (ge=0, min_length=1, etc.)
# - @field_validator for cross-type safety
# - @model_validator for cross-field invariants

AgentRole       = Literal["queen", "coordinator", "coder", "tester", "reviewer",
                          "researcher", "architect", "security", "optimizer"]
SwarmTopology   = Literal["hierarchical", "mesh", "ring", "star", "adaptive"]
ConsensusProtocol = Literal["raft", "bft", "gossip", "majority"]
AgentStatus     = Literal["idle", "working", "blocked", "done", "failed"]
TaskStatus      = Literal["pending", "assigned", "running", "completed", "failed", "cancelled"]
TaskPriority    = Literal["low", "medium", "high", "critical"]

class AgentSpec(BaseModel):              # Who an agent is
class SwarmTask(BaseModel):              # A unit of work
class AgentVote(BaseModel):              # Consensus vote from one agent
class ConsensusResult(BaseModel):        # Aggregated vote outcome
class SwarmMemoryEntry(BaseModel):       # One stored memory pattern
class SwarmMemory(BaseModel):            # The full in-process memory store
class SwarmConfig(BaseModel):            # Swarm-level configuration
class AgentState(BaseModel):             # Per-agent LangGraph node state
class SwarmState(BaseModel):             # Top-level LangGraph state (shared)
class QueenDirective(BaseModel):         # Instruction from queen to workers
class WorkerResult(BaseModel):           # Result from a worker agent
class SwarmCheckpoint(BaseModel):        # Serializable swarm snapshot
```

### 2C. LangGraph Graph Architecture

```
                    ┌──────────────┐
                    │  START       │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ route_task   │  ← Tier-1/2/3 complexity router
                    └──────┬───────┘
           ┌───────────────┼────────────────┐
           │               │                │
    ┌──────▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐
    │ fast_agent  │  │queen_node  │  │ mesh_node  │
    │ (tier-1/2) │  │(tier-3)    │  │ (peer)     │
    └──────┬──────┘  └─────┬──────┘  └─────┬──────┘
           │               │                │
           │         ┌─────▼──────┐         │
           │         │  Send()    │         │
           │         │fan-out to  │         │
           │         │N workers   │         │
           │         └─────┬──────┘         │
           │               │ (parallel)     │
           │    ┌──────────┼──────────┐     │
           │  ┌─▼──┐    ┌──▼─┐    ┌──▼─┐   │
           │  │W-1 │    │W-2 │    │W-N │   │
           │  └─┬──┘    └──┬─┘    └──┬─┘   │
           │    └──────────┼──────────┘     │
           │         ┌─────▼──────┐         │
           │         │ consensus  │         │
           │         │ _node      │         │
           │         └─────┬──────┘         │
           └───────────────┼────────────────┘
                    ┌──────▼───────┐
                    │ judge_node   │  ← Anti-drift check + SONA distill
                    └──────┬───────┘
                           │
              ┌────────────┴──────────────┐
              │ complete?                 │ needs_retry?
              │                           │
        ┌─────▼──────┐             ┌──────▼─────┐
        │  END       │             │ route_task │ (loop back)
        └────────────┘             └────────────┘
```

---

## 🔨 Phase 3 — Implementation Instructions

### Rule R1: All Pydantic Models Must Be Hardened
```python
class SwarmState(BaseModel):
    model_config = ConfigDict(
        extra='forbid',           # Reject unknown fields (checkpoint safety)
        validate_assignment=True, # Validate mutations
    )
    # No field may be bare dict[str, Any] if a typed alternative exists
```

### Rule R2: SwarmState Must Be the Single Source of Truth
- All agents read FROM `SwarmState`
- All agents write partial updates BACK TO `SwarmState` as dicts
- No agent holds private mutable state outside `SwarmState`
- `SwarmState.history` is a bounded list (max 500 entries)

### Rule R3: Queen Node Uses `Send()` for True Parallelism
```python
from langgraph.types import Send

def queen_node(state: SwarmState) -> list[Send]:
    """Decompose objective → dispatch tasks to worker subgraphs in parallel."""
    tasks = decompose_objective(state.objective, state.config.topology)
    return [
        Send("worker_node", AgentState(task=t, agent_id=f"worker-{i}"))
        for i, t in enumerate(tasks)
    ]
```

### Rule R4: Consensus Node Must Be Fault-Tolerant
```python
def consensus_node(state: SwarmState) -> dict:
    """Apply the configured consensus protocol to worker votes."""
    protocol = state.config.consensus_protocol
    votes = state.pending_votes
    if protocol == "raft":
        result = _raft_consensus(votes)          # Leader-based
    elif protocol == "bft":
        result = _bft_consensus(votes)           # 2/3 majority required
    elif protocol == "gossip":
        result = _gossip_consensus(votes)        # Eventual consistency
    else:  # majority
        result = _majority_consensus(votes)      # Simple >50%
    return {"consensus_result": result, "pending_votes": []}
```

### Rule R5: Anti-Drift Via Model Validator
```python
@model_validator(mode='after')
def _check_no_objective_drift(self) -> 'SwarmState':
    """Validate worker outputs haven't drifted from the original objective hash."""
    if self.objective_hash and self.latest_result:
        actual = hashlib.sha256(self.latest_result.encode()).hexdigest()[:16]
        if not _objectives_aligned(self.objective, self.latest_result):
            raise ValueError(
                f"Objective drift detected: result does not satisfy original objective. "
                f"Objective hash: {self.objective_hash}"
            )
    return self
```

### Rule R6: Memory Must Be Persisted Across Workflow Runs
```python
class SwarmMemory(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entries: list[SwarmMemoryEntry] = Field(default_factory=list)
    namespace: str = "default"

    def search(self, query: str, top_k: int = 5) -> list[SwarmMemoryEntry]:
        """Semantic search — cosine similarity over embeddings if available,
        else keyword fallback."""
        ...

    def store(self, key: str, value: str, score: float = 1.0) -> None:
        """Add or update a memory entry."""
        ...

    def distill(self) -> list[SwarmMemoryEntry]:
        """SONA-style: keep only high-score entries, merge duplicates."""
        ...
```

### Rule R7: 3-Tier Routing Must Be a Conditional Edge
```python
def route_task(state: SwarmState) -> str:
    """Return node name based on task complexity score."""
    score = _complexity_score(state.current_task)
    if score < 0.15:
        return "fast_agent"          # Tier 1: heuristic / template
    elif score < 0.50:
        return "medium_agent"        # Tier 2: single LLM call
    else:
        topology = state.config.topology
        return f"{topology}_queen"   # Tier 3: full swarm

builder.add_conditional_edges("route_task", route_task, {
    "fast_agent":         "fast_agent",
    "medium_agent":       "medium_agent",
    "hierarchical_queen": "hierarchical_queen",
    "mesh_queen":         "mesh_queen",
    ...
})
```

### Rule R8: SONA Self-Learning Loop Must Close
```python
# After every completed swarm run:
def distill_node(state: SwarmState) -> dict:
    """SONA: RETRIEVE → JUDGE → DISTILL → CONSOLIDATE → ROUTE."""
    lesson = _extract_lesson(state)
    if lesson and state.memory.should_store(lesson):
        state.memory.store(
            key=f"pattern:{state.objective_hash}",
            value=lesson.summary,
            score=lesson.confidence,
        )
    return {"memory": state.memory, "sona_distilled": True}
```

### Rule R9: Topology-Specific Graph Builders
```python
def build_swarm_graph(config: SwarmConfig) -> CompiledGraph:
    """Build the correct LangGraph topology from config."""
    if config.topology == "hierarchical":
        return _build_hierarchical_graph(config)
    elif config.topology == "mesh":
        return _build_mesh_graph(config)
    elif config.topology == "ring":
        return _build_ring_graph(config)
    elif config.topology == "star":
        return _build_star_graph(config)
    elif config.topology == "adaptive":
        return _build_adaptive_graph(config)
    raise ValueError(f"Unknown topology: {config.topology}")
```

### Rule R10: Human-in-the-Loop Via `interrupt()`
```python
def approval_node(state: SwarmState) -> dict:
    """Pause for human review before executing high-risk consensus decisions."""
    if state.consensus_result and state.consensus_result.requires_approval:
        payload = interrupt({
            "swarm_id": state.swarm_id,
            "objective": state.objective,
            "proposed_action": state.consensus_result.action,
            "agent_votes": [v.model_dump() for v in state.pending_votes],
        })
        decision = payload.get("decision", "deny")
        if decision != "approve":
            return {"status": "denied", "consensus_result": None}
    return {}   # Pass through if no approval needed
```

---

## 📝 Phase 4 — Detailed Implementation Specification

### 4A. File Structure to Create

```
swarm/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── agent.py          ← AgentSpec, AgentState, AgentRole, AgentVote, WorkerResult
│   ├── task.py           ← SwarmTask, TaskStatus, TaskPriority, QueenDirective
│   ├── state.py          ← SwarmState (main LangGraph state), SwarmCheckpoint
│   ├── memory.py         ← SwarmMemoryEntry, SwarmMemory (SONA loop)
│   ├── config.py         ← SwarmConfig, ConsensusProtocol, SwarmTopology
│   └── consensus.py      ← ConsensusResult, AgentVote aggregation
├── nodes/
│   ├── __init__.py
│   ├── router.py         ← route_task() — 3-tier complexity routing
│   ├── queen.py          ← queen_node() — objective decomposition + Send()
│   ├── workers.py        ← worker_node() — per-agent execution
│   ├── consensus.py      ← consensus_node() — raft/bft/gossip/majority
│   ├── judge.py          ← judge_node() — anti-drift + SONA distill
│   ├── memory.py         ← memory_node() — store/retrieve/distill
│   └── approval.py       ← approval_node() — interrupt() gate
├── graphs/
│   ├── __init__.py
│   ├── hierarchical.py   ← build_hierarchical_graph()
│   ├── mesh.py           ← build_mesh_graph()
│   ├── ring.py           ← build_ring_graph()
│   ├── star.py           ← build_star_graph()
│   ├── adaptive.py       ← build_adaptive_graph()
│   └── factory.py        ← build_swarm_graph(config) → dispatch
├── consensus/
│   ├── __init__.py
│   ├── raft.py           ← Raft leader-based consensus
│   ├── bft.py            ← Byzantine Fault Tolerance (2/3 majority)
│   ├── gossip.py         ← Eventual consistency gossip
│   └── majority.py       ← Simple majority vote
├── memory/
│   ├── __init__.py
│   ├── store.py          ← SwarmMemoryStore (in-process + optional vector backend)
│   ├── sona.py           ← SONA learning loop implementation
│   └── hnsw_adapter.py   ← Optional HNSW/vector backend adapter
└── tests/
    ├── test_models.py
    ├── test_consensus.py
    ├── test_topologies.py
    ├── test_sona_loop.py
    └── test_swarm_e2e.py
```

### 4B. SwarmState — Full Specification

```python
class SwarmState(BaseModel):
    """
    The canonical shared state for a LangGraph swarm workflow.
    
    Maps to Ruflo's swarm coordination layer:
    - swarm_id       ↔  Ruflo swarm session ID
    - topology       ↔  Ruflo topology (hierarchical/mesh/ring/star/adaptive)
    - agents         ↔  Ruflo spawned agent pool
    - tasks          ↔  Ruflo task queue
    - memory         ↔  Ruflo AgentDB/HNSW memory layer
    - consensus_result ↔ Ruflo Raft/BFT/Gossip consensus output
    - sona_*         ↔  Ruflo SONA self-learning state
    - objective_hash ↔  Ruflo anti-drift reference hash
    """

    model_config = ConfigDict(extra='forbid', validate_assignment=True)

    # Identity
    swarm_id: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    objective_hash: str = ""              # SHA-256[:16] of original objective

    # Configuration
    config: SwarmConfig

    # Agent pool
    agents: list[AgentSpec] = Field(default_factory=list)
    max_agents: int = Field(default=8, ge=1, le=100)

    # Task management
    tasks: list[SwarmTask] = Field(default_factory=list)
    current_task: SwarmTask | None = None
    completed_tasks: list[SwarmTask] = Field(default_factory=list)

    # Consensus
    pending_votes: list[AgentVote] = Field(default_factory=list)
    consensus_result: ConsensusResult | None = None

    # Results
    worker_results: list[WorkerResult] = Field(default_factory=list)
    latest_result: str = ""
    final_output: str = ""

    # Memory / SONA
    memory: SwarmMemory = Field(default_factory=SwarmMemory)
    sona_distilled: bool = False
    sona_cycle_count: int = Field(default=0, ge=0)

    # Status
    status: SwarmStatus = "initializing"
    failure_cause: SwarmFailureCause | None = None
    iteration: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=10, ge=1, le=50)

    # History (bounded, ≤500 entries)
    history: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Timestamps
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # Anti-drift
    @field_validator("objective")
    @classmethod
    def _set_objective_hash(cls, v: str) -> str:
        return v  # hash set in model_validator below

    @model_validator(mode="after")
    def _init_objective_hash(self) -> "SwarmState":
        if not self.objective_hash and self.objective:
            self.objective_hash = hashlib.sha256(
                self.objective.encode()
            ).hexdigest()[:16]
        return self

    @model_validator(mode="after")
    def _cap_history(self) -> "SwarmState":
        if len(self.history) > 500:
            self.history = self.history[:1] + self.history[-499:]
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
        return self
```

### 4C. SwarmConfig — Full Specification

```python
class SwarmConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    topology: SwarmTopology = "hierarchical"
    consensus_protocol: ConsensusProtocol = "raft"
    max_agents: int = Field(default=8, ge=1, le=100)
    strategy: Literal["development", "research", "security", "specialized"] = "development"

    # Anti-drift
    anti_drift_enabled: bool = True
    checkpoint_every_n_tasks: int = Field(default=1, ge=1)

    # 3-Tier routing thresholds
    tier1_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    tier2_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    # Memory
    memory_namespace: str = Field(default="default", min_length=1)
    memory_max_entries: int = Field(default=1000, ge=10)
    sona_enabled: bool = True
    sona_min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    # Consensus
    bft_quorum_fraction: float = Field(default=0.67, ge=0.51, le=1.0)
    raft_heartbeat_ms: int = Field(default=150, ge=50, le=5000)

    # Human-in-the-loop
    require_approval_above_risk: float = Field(default=0.8, ge=0.0, le=1.0)
```

### 4D. Consensus Implementations

#### Raft (Leader-Based — Default for Hierarchical)
```python
def _raft_consensus(votes: list[AgentVote]) -> ConsensusResult:
    """Leader (queen) has authoritative state. Workers validate against it.
    Queen vote always wins if present; otherwise simple majority."""
    queen_votes = [v for v in votes if v.agent_role == "queen"]
    if queen_votes:
        winner = queen_votes[0]
        return ConsensusResult(
            action=winner.proposed_action,
            protocol="raft",
            vote_count=len(votes),
            agreement_fraction=1.0,
            authoritative=True,
        )
    return _majority_consensus(votes)
```

#### BFT (Byzantine Fault Tolerance — for Star/High-Stakes)
```python
def _bft_consensus(votes: list[AgentVote], quorum: float = 0.67) -> ConsensusResult:
    """Requires 2/3 supermajority. Tolerates up to 1/3 faulty agents."""
    counter = Counter(v.proposed_action for v in votes)
    threshold = math.ceil(len(votes) * quorum)
    for action, count in counter.most_common():
        if count >= threshold:
            return ConsensusResult(
                action=action,
                protocol="bft",
                vote_count=len(votes),
                agreement_fraction=count / len(votes),
                authoritative=True,
            )
    return ConsensusResult(
        action=None,
        protocol="bft",
        vote_count=len(votes),
        agreement_fraction=0.0,
        authoritative=False,
        failed=True,
    )
```

#### Gossip (Eventual Consistency — for Mesh)
```python
def _gossip_consensus(votes: list[AgentVote]) -> ConsensusResult:
    """Weight votes by agent confidence score. No hard quorum."""
    weighted: dict[str, float] = defaultdict(float)
    for v in votes:
        weighted[v.proposed_action] += v.confidence
    total = sum(weighted.values())
    best_action = max(weighted, key=weighted.__getitem__)
    return ConsensusResult(
        action=best_action,
        protocol="gossip",
        vote_count=len(votes),
        agreement_fraction=weighted[best_action] / total if total else 0.0,
        authoritative=False,
    )
```

---

## 🧪 Phase 5 — Test Specifications

Write pytest tests that verify:

### 5A. Model Tests (`test_models.py`)
- `SwarmState` rejects unknown fields (`extra='forbid'`)
- `SwarmState.objective_hash` is auto-computed from `objective`
- `SwarmState.history` is capped at 500 entries
- `SwarmConfig` is frozen (immutable after creation)
- `SwarmConfig.tier1_threshold < tier2_threshold` (add `@model_validator`)
- `AgentVote.confidence` is in `[0.0, 1.0]`
- `WorkerResult` with `exit_code=-1` is rejected (`ge=0` constraint)

### 5B. Consensus Tests (`test_consensus.py`)
- Raft: queen vote always wins
- Raft: no queen → majority wins
- BFT: requires ≥67% supermajority
- BFT: <67% returns `failed=True`
- Gossip: highest weighted action wins
- Majority: simple >50% threshold
- Edge case: all votes tied → defined behavior (not exception)
- Edge case: single voter → succeeds

### 5C. Topology Tests (`test_topologies.py`)
- `build_swarm_graph(hierarchical_config)` produces a compiled graph
- Hierarchical graph has `queen_node` → `Send()` → `worker_nodes`
- Mesh graph has peer-to-peer edges, no single queen
- Ring graph has sequential A → B → C edges
- 3-tier routing: complexity 0.1 → `fast_agent`
- 3-tier routing: complexity 0.7 → queen/swarm
- Anti-drift: drifted result raises `ValidationError`

### 5D. SONA Loop Tests (`test_sona_loop.py`)
- Memory `store()` → `search()` returns stored entry
- Memory `distill()` removes low-confidence entries
- Memory is bounded to `max_entries`
- SONA cycle count increments per `distill_node` call
- High-confidence lesson persisted; low-confidence discarded

### 5E. End-to-End Tests (`test_swarm_e2e.py`)
- Hierarchical swarm with 3 workers completes `status="completed"`
- Failed worker does not block swarm if consensus achieved
- `interrupt()` approval gate pauses execution
- `Command(resume="approve")` resumes and completes
- Swarm state checkpointed and reloadable mid-run
- Memory lessons from run-1 are retrieved in run-2

---

## ✅ Phase 6 — Validation Checklist

Before marking implementation complete:

**Pydantic Models**
- [ ] `SwarmState` has `extra='forbid'` and `validate_assignment=True`
- [ ] `SwarmConfig` has `frozen=True`
- [ ] All numeric fields have `ge=` / `le=` bounds
- [ ] `objective_hash` auto-set in `@model_validator`
- [ ] `history` and `errors` lists are bounded
- [ ] `AgentVote.confidence` constrained to `[0.0, 1.0]`
- [ ] No bare `dict[str, Any]` where a typed model is possible

**LangGraph Graph**
- [ ] `queen_node` uses `Send()` for true parallel fan-out
- [ ] `consensus_node` supports all 4 protocols via config
- [ ] `route_task` conditional edge covers all topology branches
- [ ] `judge_node` enforces anti-drift check
- [ ] `approval_node` uses `interrupt()` correctly
- [ ] Graph compiles without errors (`builder.compile(checkpointer=...)`)
- [ ] State round-trips through `model_dump(mode='json')` + `model_validate()`

**Swarm Invariants (Ruflo-inspired)**
- [ ] Queen is always present in hierarchical topology
- [ ] Worker count never exceeds `SwarmConfig.max_agents`
- [ ] Consensus never proceeds with zero votes
- [ ] BFT consensus fails gracefully (no exception) when quorum not reached
- [ ] SONA loop runs after every completed swarm cycle
- [ ] Memory is persisted to checkpoint; survives workflow restart
- [ ] Anti-drift: any result hash mismatch blocks state transition

**Testing**
- [ ] All 5 test modules have ≥ 10 test cases each
- [ ] Consensus edge cases (tie, single vote, all-fail) tested
- [ ] Topology factories tested for all 5 topologies
- [ ] E2E test with real `InMemorySaver` checkpointer
- [ ] `pytest -q` passes with no failures

---

## 📎 Reference: Key Ruflo → Python Mappings

```python
# Ruflo CLI → Python equivalent
# npx claude-flow swarm init --topology hierarchical --max-agents 8
config = SwarmConfig(topology="hierarchical", max_agents=8)
state  = SwarmState(swarm_id="s1", objective="...", config=config)
graph  = build_swarm_graph(config)

# npx claude-flow agent spawn --type coder --name coder-1
agent = AgentSpec(agent_id="coder-1", role="coder", name="coder-1")
state.agents.append(agent)

# npx claude-flow swarm start --objective "fix failing tests"
result_state = graph.invoke(state.model_dump(mode='json'),
                            config={"configurable": {"thread_id": state.swarm_id}})

# npx claude-flow memory store --key "pattern-x" --value "..."
state.memory.store(key="pattern-x", value="what worked", score=0.9)

# npx claude-flow memory search --query "..."
matches = state.memory.search(query="authentication patterns", top_k=5)

# npx claude-flow hive-mind --topology hierarchical --consensus raft
config = SwarmConfig(topology="hierarchical", consensus_protocol="raft")

# Anti-drift checkpoint (post-task hook equivalent)
state.config.checkpoint_every_n_tasks = 1  # Checkpoint after every task

# 3-tier routing equivalent
# Tier 1: fast_agent node (heuristic, no LLM)
# Tier 2: medium_agent node (single LLM call)
# Tier 3: queen_node + Send() fan-out (full swarm)
```

---

## 🔧 Quick-Start Template

After implementing all phases, the usage should look like:

```python
from swarm import build_swarm_graph
from swarm.models import SwarmConfig, SwarmState

# 1. Configure the swarm (Ruflo-style)
config = SwarmConfig(
    topology="hierarchical",
    consensus_protocol="raft",
    max_agents=8,
    strategy="development",
    anti_drift_enabled=True,
    sona_enabled=True,
)

# 2. Initialize state (Ruflo: swarm init)
state = SwarmState(
    swarm_id="fix-tests-001",
    objective="Fix all failing pytest tests in src/",
    config=config,
)

# 3. Build the graph (Ruflo: swarm start)
graph = build_swarm_graph(config)

# 4. Run (Ruflo: swarm start --objective "..." --strategy development)
from langgraph.checkpoint.memory import InMemorySaver
checkpointer = InMemorySaver()
app = graph.compile(checkpointer=checkpointer)

result = app.invoke(
    state.model_dump(mode="json"),
    config={"configurable": {"thread_id": state.swarm_id}},
)

# 5. Parse typed result
final = SwarmState.model_validate(result)
print(f"Status: {final.status}")
print(f"Output: {final.final_output}")
print(f"Memory lessons learned: {len(final.memory.entries)}")
```
