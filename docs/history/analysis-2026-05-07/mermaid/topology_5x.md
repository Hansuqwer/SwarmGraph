# Topology Diagrams — Intent vs Reality

> All 5 topologies share the same underlying LangGraph shape (parallel Send fan-out + collect + consensus). Only the **role mix** in the worker set varies. See `agents/agent_25_topology.md` finding 25-CORR1.

## Hierarchical (default) — INTENT vs REALITY: matches

```mermaid
graph TD
    Q[hierarchical_queen]
    R[researcher]
    A[architect]
    C[coder]
    T[tester]
    V[reviewer]
    CN[consensus_node]
    Q -->|Send| R
    Q -->|Send| A
    Q -->|Send| C
    Q -->|Send| T
    Q -->|Send| V
    R --> CN
    A --> CN
    C --> CN
    T --> CN
    V --> CN
```

## Mesh — INTENT (peer-to-peer)
```mermaid
graph LR
    C[coder] --- T[tester]
    T --- V[reviewer]
    V --- R[researcher]
    R --- C
    C --- V
    T --- R
```

## Mesh — REALITY (parallel fan-out, identical task strings)
```mermaid
graph TD
    Q[mesh_queen]
    Q -->|Send 'collaborate'| C[coder]
    Q -->|Send 'collaborate'| T[tester]
    Q -->|Send 'collaborate'| V[reviewer]
    Q -->|Send 'collaborate'| R[researcher]
    C --> CN[consensus_node]
    T --> CN
    V --> CN
    R --> CN
```

## Ring — INTENT (sequential pipeline)
```mermaid
graph LR
    R[researcher] --> C[coder] --> T[tester] --> V[reviewer]
```

## Ring — REALITY (parallel)
```mermaid
graph TD
    Q[ring_queen]
    Q -->|Send| R[researcher]
    Q -->|Send| C[coder]
    Q -->|Send| T[tester]
    Q -->|Send| V[reviewer]
    R --> CN[consensus_node]
    C --> CN
    T --> CN
    V --> CN
```

## Star — INTENT (central hub + isolated spokes)
```mermaid
graph TD
    H[hub] --- S1[security]
    H --- S2[optimizer]
    H --- S3[architect]
    H --- S4[coder]
```

## Star — REALITY (parallel)
```mermaid
graph TD
    Q[star_queen]
    Q -->|Send| S1[security]
    Q -->|Send| S2[optimizer]
    Q -->|Send| S3[architect]
    Q -->|Send| S4[coder]
    S1 --> CN[consensus_node]
    S2 --> CN
    S3 --> CN
    S4 --> CN
```

## Adaptive — INTENT (escalates based on prior consensus)
```mermaid
graph TD
    A[adaptive_queen]
    A -->|low agreement?| M[switch to mesh]
    A -->|high agreement?| H[stay hierarchical]
```

## Adaptive — REALITY (silently aliased to hierarchical)
```mermaid
graph TD
    A[adaptive_queen]
    A -->|always| H[_hierarchical_decompose]
```

**Recommendation:** either implement true ring/mesh/star/adaptive, OR rename topologies to `role_set_*` to honestly reflect they only vary the worker role mix.
