# Import Graph — `hive-swarm/swarm/`

```mermaid
graph TD
    init["__init__.py<br/>(public API)"]

    subgraph models
        base[base.py<br/>HardenedModel, FrozenModel]
        types[types.py<br/>Literal aliases]
        agent[agent.py<br/>AgentSpec, AgentVote, WorkerResult]
        task[task.py<br/>SwarmTask, QueenDirective]
        config[config.py<br/>SwarmConfig]
        consensus_m[consensus.py<br/>ConsensusResult + 4 protocols]
        memory[memory.py<br/>SwarmMemory, VectorAdapter]
        state[state.py<br/>SwarmState, SwarmCheckpoint]
    end

    subgraph nodes
        router[router.py]
        queen[queen.py]
        worker[worker.py]
        consensus_n[consensus.py]
        judge[judge.py]
        approval[approval.py]
        sona[sona.py]
        checkpointing[checkpointing.py]
    end

    subgraph graphs
        factory[factory.py<br/>build_swarm_graph]
    end

    base --> agent
    base --> task
    base --> config
    base --> consensus_m
    base --> memory
    base --> state
    types --> agent
    types --> task
    types --> config
    types --> consensus_m
    types --> state
    agent --> consensus_m
    agent --> state
    config --> state
    consensus_m --> state
    memory --> state
    task --> state

    state --> router
    state --> queen
    state --> worker
    state --> consensus_n
    state --> judge
    state --> approval
    state --> sona
    state --> checkpointing
    consensus_m --> consensus_n
    agent --> queen
    task --> queen

    router --> factory
    queen --> factory
    worker --> factory
    consensus_n --> factory
    judge --> factory
    approval --> factory
    sona --> factory
    checkpointing --> factory

    factory --> init
    state --> init
    config --> init
    agent --> init
    task --> init
    memory --> init
    consensus_m --> init
    types --> init
    checkpointing --> init
```

**Verdict:** clean DAG, no cycles. Public API surface (`__init__.py`) imports from every layer; internal layers respect strict ordering: `models → nodes → graphs`.
