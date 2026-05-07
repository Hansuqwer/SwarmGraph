# Ruflo Research Notes — Swarm Architecture Deep Dive

> Source: https://github.com/ruvnet/ruflo (46k ⭐, 5.1k forks, 6,300+ commits)
> Also known as: claude-flow v3.5/v3.6, 314 MCP tools, 250k+ lines TypeScript + WASM

---

## What Is Ruflo?

Ruflo (formerly Claude-Flow) is an **enterprise-grade multi-agent orchestration platform** for Claude Code and Codex. It adds a *nervous system* to LLM coding agents:

```
User → Ruflo (CLI/MCP) → Router → Swarm → Agents → Memory → LLM Providers
              ↑                                                      │
              └──────────── Learning Loop (SONA) ◄──────────────────┘
```

**Key insight**: Ruflo separates *orchestration* from *execution*. The orchestrator (Ruflo) tracks state, coordinates, and learns. The executor (Claude/Codex) writes code and runs commands.

---

## Core Architecture Layers

### Layer 1 — Entry / Security
- **CLI / MCP Server**: Exposes 314 MCP tools + 26 CLI commands
- **AIDefence**: Detects prompt injection, jailbreak, PII — <10ms, 50+ patterns

### Layer 2 — Routing
- **Q-Learning Router**: 89% accuracy routing to right agent/tier
- **MoE (Mixture of Experts)**: 8 expert networks for specialized domains
- **Skills** (130+): Domain-specific knowledge injected at routing time
- **Hooks** (17 + 12 workers): Pre/post task automation

### Layer 3 — Swarm Coordination
- **Topologies**: hierarchical, mesh, ring, star, adaptive/hybrid
- **Consensus**: Raft, BFT, Gossip, CRDT
- **Claims**: Human-Agent coordination (approval gates)

### Layer 4 — Agent Pool (100+ types)
Organized into 8 categories:
- Core: coder, reviewer, tester, planner, researcher
- SPARC: specification, pseudocode, architecture, refinement
- Swarm: hierarchical-coordinator, mesh-coordinator, adaptive-coordinator
- Consensus: byzantine-coordinator, raft-manager, gossip-coordinator, crdt-synchronizer
- GitHub: pr-manager, issue-tracker, release-manager
- Security: security-architect, security-auditor
- Performance: perf-analyzer, performance-benchmarker
- Specialized: backend-dev, mobile-dev, ml-developer

### Layer 5 — Memory & Learning (RuVector Intelligence Layer)
- **HNSW Vector Index**: 150x–12,500x faster than naive search
- **SONA** (Self-Optimising Neural Analysis): <0.05ms adaptation
- **EWC++** (Elastic Weight Consolidation): Prevents catastrophic forgetting
- **Flash Attention**: 2.49–7.47x speedup
- **ReasoningBank**: Pattern distillation store
- **AgentDB**: SQLite-backed with 20+ memory controllers
- **MemoryGraph**: PageRank + community detection on insights
- **9 RL Algorithms**: Q-Learning, SARSA, PPO, DQN, A3C, SAC, TD3, DDPG, Rainbow

---

## Swarm Topologies — Detailed

### Hierarchical (Default for Coding)
```
Strategic Queen
    ├── Tactical Queen (Domain A)
    │       ├── Worker: coder-1
    │       ├── Worker: tester-1
    │       └── Worker: reviewer-1
    └── Tactical Queen (Domain B)
            ├── Worker: architect-1
            └── Worker: security-1
```
- **Consensus**: Raft (leader-based, queen = leader)
- **Anti-drift**: Queen validates all outputs against objective
- **Best for**: 6–8 agents, structured coding tasks
- **Drift prevention**: Frequent checkpoints via `post-task` hooks

### Mesh (Peer Collaboration)
```
Agent-A ─── Agent-B
   │    ╲  ╱    │
   │     ╲╱     │
   │     ╱╲     │
Agent-C ─── Agent-D
```
- **Consensus**: Gossip (eventual consistency)
- **Best for**: High-redundancy collaborative tasks, 4+ agents
- **Drift risk**: Medium — no central authority

### Ring (Sequential Pipeline)
```
Agent-A → Agent-B → Agent-C → Agent-D → Agent-A (loop)
```
- **Consensus**: Gossip
- **Best for**: Linear pipelines, 3+ agents
- **Performance**: 0.12s coordination overhead

### Star (Centralized Hub)
```
          Hub
         /│\ \
        / │ \  \
   W-1 W-2 W-3 W-4
```
- **Consensus**: BFT (Byzantine Fault Tolerant)
- **Best for**: Centralized control plane, audit workflows
- **Fault tolerance**: Up to 1/3 faulty agents tolerated

### Adaptive (Dynamic)
- Monitors performance metrics at runtime
- Switches topology based on task complexity and agent load
- Starts simple (ring/star), upgrades to hierarchical as needed

---

## Consensus Protocols — Detailed

### Raft (Leader Election + Log Replication)
- Queen = permanent leader (no election in Ruflo's implementation)
- All state changes go through leader
- Workers acknowledge before state is committed
- **Guarantees**: Strong consistency, no split-brain
- **Use**: Hierarchical coding swarms

### BFT (Byzantine Fault Tolerance)
- Requires **2/3 supermajority** (e.g., 5 of 7 agents must agree)
- Tolerates up to 1/3 faulty/malicious agents
- Three phases: Pre-prepare → Prepare → Commit
- **Guarantees**: Safety even with compromised agents
- **Use**: High-stakes decisions, star topology

### Gossip (Epidemic Protocol)
- Agents propagate state to random neighbors
- Eventually all agents converge to same state
- Weighted by agent confidence scores
- **Guarantees**: Eventual consistency (not strong)
- **Use**: Mesh topology, exploratory tasks

### CRDT (Conflict-free Replicated Data Types)
- Mathematically merge-able data structures
- No coordinator needed — all merges are valid
- **Guarantees**: Convergence without coordination
- **Use**: Distributed memory synchronization

---

## SONA Self-Learning Loop

```
RETRIEVE → JUDGE → DISTILL → CONSOLIDATE → ROUTE
   ↑                                           │
   └───────────────────────────────────────────┘
```

1. **RETRIEVE**: Query AgentDB/HNSW for patterns matching current task
2. **JUDGE**: Score retrieved patterns for relevance (cosine similarity + PageRank)
3. **DISTILL**: Extract generalizable rules from successful executions
4. **CONSOLIDATE**: Merge new patterns with existing ReasoningBank (EWC++ prevents forgetting)
5. **ROUTE**: Update Q-Learning routing table — route similar future tasks differently

**Performance**: <0.05ms per SONA adaptation cycle

---

## 3-Tier Model Routing

```
Task Complexity Score (0.0 – 1.0)
         │
         ├── < 0.15 → Tier 1: Agent Booster (WASM)
         │            No LLM call. <1ms. $0.
         │            Intent types: var-to-const, add-types, add-error-handling
         │
         ├── 0.15–0.50 → Tier 2: Haiku / Sonnet
         │               Single LLM call. ~500ms. $0.0002.
         │               Simple tasks, documentation, low-risk changes.
         │
         └── > 0.50 → Tier 3: Opus + Swarm
                       Multiple LLM calls via spawned swarm.
                       2-5s. Complex reasoning, architecture, security.
```

---

## Anti-Drift Protocol

Ruflo's anti-drift system prevents agents from gradually deviating from the original objective:

1. **Objective Hash**: SHA-256 of original objective stored at swarm init
2. **Post-task validation**: Each worker output is semantically checked against objective
3. **Coordinator validation**: Hierarchical coordinator compares outputs to original goal
4. **Raft checkpoints**: Leader maintains authoritative state; workers must re-sync if they drift
5. **Short task cycles**: Tasks are broken into small units with frequent verification gates

**Config** (from CLAUDE.md):
```javascript
mcp__ruv-swarm__swarm_init({
  topology: "hierarchical",
  maxAgents: 8,
  strategy: "specialized"  // clear role boundaries
})
// + post-task hooks for checkpoint frequency
// + shared memory namespace for all agents
```

---

## Hive-Mind System

Three queen types form the collective intelligence:

| Queen Type | Role | Scope |
|---|---|---|
| Strategic Queen | Sets overall objective, allocates domains | Entire swarm |
| Tactical Queen | Decomposes domain objectives into tasks | Domain (e.g., backend) |
| Adaptive Worker | Executes tasks, reports results, learns | Individual tasks |

**Collective Memory**: LRU-cached with SQLite persistence. All queens share read access. Write access gated by Raft consensus.

---

## What Ruflo Does NOT Do (Important for Port)

From `AGENTS.md`:
> "claude-flow = LEDGER (tracks state, stores memory, coordinates)"
> "Codex / Claude = EXECUTOR (writes code, runs commands, creates files)"

Ruflo **does not execute code**. It is a **coordination ledger**. The actual work is done by the LLM agents (Claude Code, Codex). This maps perfectly to LangGraph:
- Ruflo = LangGraph's StateGraph + checkpointer
- Agents = LangGraph's node functions
- Memory = LangGraph's state + external store
- Swarm = LangGraph's subgraphs + `Send()` fan-out

---

## Key MCP Tools (Map to Python Functions)

| MCP Tool | Ruflo Purpose | Python Equivalent |
|---|---|---|
| `swarm_init(topology, maxAgents)` | Initialize swarm | `SwarmState(config=SwarmConfig(...))` |
| `agent_spawn(type, name)` | Register agent | `state.agents.append(AgentSpec(...))` |
| `swarm_status()` | Check swarm | `state.status` |
| `task_orchestrate(...)` | Coordinate tasks | `queen_node(state)` → `Send()` |
| `memory_store(key, value, namespace)` | Store pattern | `state.memory.store(key, value)` |
| `memory_search(query)` | Retrieve pattern | `state.memory.search(query)` |
| `hive_mind_spawn(topology, consensus)` | Queen hierarchy | `build_hierarchical_graph(config)` |

---

## Port Priority Matrix

| Ruflo Feature | Python Port Priority | Complexity | Value |
|---|---|---|---|
| Hierarchical topology | 🔴 Must-Have | Medium | Very High |
| 3-tier routing | 🔴 Must-Have | Low | Very High |
| Raft consensus | 🔴 Must-Have | Medium | High |
| Anti-drift validation | 🔴 Must-Have | Low | High |
| In-process memory + search | 🔴 Must-Have | Low | High |
| Mesh topology | 🟠 Should-Have | Medium | High |
| BFT consensus | 🟠 Should-Have | Medium | Medium |
| SONA self-learning loop | 🟠 Should-Have | High | High |
| Ring/Star topologies | 🟡 Nice-to-Have | Low | Medium |
| HNSW vector backend | 🟡 Nice-to-Have | High | Medium |
| Adaptive topology | 🟡 Nice-to-Have | High | Medium |
| Multi-provider LLM routing | 🟡 Nice-to-Have | Medium | Medium |
| Agent Federation (cross-machine) | 🟢 Future | Very High | Medium |
