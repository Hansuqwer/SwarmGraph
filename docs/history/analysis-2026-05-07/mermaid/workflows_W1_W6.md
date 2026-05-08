# Workflow Diagrams W1–W6

## W1 — `hive-swarm` happy path
```mermaid
graph TD
    START([START])
    MR[memory_retrieve<br/>SONA RETRIEVE]
    RT[router_node<br/>complexity score]
    F[fast_agent<br/>Tier 1]
    M[medium_agent<br/>Tier 2]
    Q[hierarchical_queen<br/>Send fan-out]
    W1[worker_node × N]
    CR[collect_results]
    CN[consensus_node<br/>raft/bft/gossip/majority]
    AP[approval_node<br/>HITL if risk≥0.8]
    JN[judge_node<br/>anti-drift]
    DN[distill_node<br/>SONA DISTILL+CONSOLIDATE]
    END([END])
    START --> MR --> RT
    RT -->|tier1| F --> DN
    RT -->|tier2| M --> DN
    RT -->|tier3| Q -.Send.-> W1 --> CR --> CN
    CN -->|low risk| JN
    CN -->|high risk| AP
    CN -->|failed| END
    AP -->|approve| JN
    AP -->|deny| END
    JN -->|drift_detected + retry available| RT
    JN -->|drift + max iter| END
    JN -->|accepted| DN
    DN --> END
```

## W2 — `hive-swarm` HITL
```mermaid
sequenceDiagram
    participant G as Graph
    participant CN as consensus_node
    participant AP as approval_node
    participant H as Human Reviewer
    participant CK as Checkpointer

    G->>CN: votes
    CN->>CN: requires_approval = (1-agreement) >= 0.8
    CN->>AP: status="awaiting_approval"
    AP->>CK: checkpoint state
    AP->>H: interrupt({swarm_id, action, risk_score, ...})
    Note over AP,H: graph paused
    H->>G: invoke(Command(resume={"decision":"approve"}))
    G->>AP: re-runs from top, interrupt() returns payload
    AP->>AP: status="judging"
    AP->>JN: continue to judge_node
```

## W3 — `ai-coder` LangGraph runtime
```mermaid
graph TD
    S([START]) --> P[plan_node]
    P --> PP[propose_patch_node<br/>returns tuple state, patch]
    PP --> VP[validate_patch_node<br/>shell-meta + denied-path checks]
    VP -->|cmd needs approval| AW[awaiting_approval<br/>interrupt]
    AW --> RT[run_tests_node]
    VP -->|no approval needed| RT
    RT --> RV[review_node]
    RV -->|tests passed + reviewer ok| END([END])
    RV -->|tests failed| FC[fail_closed<br/>tests_failed]
    FC --> END
```

## W4 — `ai-coder` legacy fallback
```mermaid
graph TD
    I[import langgraph] --> Q{available?}
    Q -->|yes| LG[LangGraphRuntime]
    Q -->|no, ModuleNotFoundError| LEG[Legacy AgentWorkflow]
    LG --> WS[WorkflowState]
    LEG --> WS
    WS -->|same schema| LCS[LocalCheckpointStore<br/>JSON artefact]
    WS -->|same schema| RCS[Sqlite/Postgres via RedactingCheckpointer]
```

## W5 — `ai-provider-swarm-gateway` 9-node
```mermaid
graph LR
    I[intake] --> CL[classify]
    CL --> PF[provider_filter]
    PF --> QC[quota_check]
    QC --> SR[swarm_route]
    SR --> CO[consensus]
    CO --> PC[provider_call]
    PC --> RV[response_validation]
    RV --> UU[usage_update]
    UU --> END([END])

    PF -.no candidates.-> END
    QC -.all exhausted.-> END
    CO -.policy-blocked.-> END
    PC -.adapter timeout.-> PC
    RV -.malformed.-> END
```

## W6 — Cross-project memory portability
```mermaid
graph LR
    AC[ai-coder<br/>MemoLesson] -->|adapter| SE[SwarmMemoryEntry]
    SE -->|hive-swarm| SM[SwarmMemory]
    SM -.no reverse adapter.- AC
    note[strict MemoLesson validators<br/>reject most code-content<br/>= one-way only]
```
