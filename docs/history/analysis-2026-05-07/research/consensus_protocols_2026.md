# Research — Multi-Agent Consensus Protocols (2025–2026 State of the Art)

> Anchors the **CORR** findings for Layer D agents (21–25).

## Why classical protocols need adaptation for LLM swarms

Traditional Raft/Paxos/PBFT achieve **binary** agreement on opaque values. LLM agents need **semantic** agreement on natural-language outputs. This means:

- "Action equality" cannot rely on byte-equality — two semantically-equivalent paraphrases lose votes.
- Confidence scores from agents are noisy and must be normalised before weighting.
- Byzantine voters in an LLM context = hallucinating agents, not adversarial nodes.

Source: *Consensus Protocols for Multi-Agent Systems — 2026 Guide* (`fast.io/resources/consensus-protocols-multi-agent-systems/`, Feb 2026).

## Protocol cheat-sheet (matches `hive-swarm/swarm/models/consensus.py`)

| Protocol | Quorum | Tolerates | Best topology | Implemented? |
|---|---|---|---|---|
| **Raft** | leader + majority | crash faults | hierarchical | ✅ `raft_consensus()` (queen-authoritative) |
| **PBFT / BFT** | ≥ 2f+1 of 3f+1 (≥ 0.67) | Byzantine (lying) faults | star | ✅ `bft_consensus()` |
| **Gossip** | none (eventual) | partial partition | mesh | ✅ `gossip_consensus()` (confidence-weighted) |
| **Majority** | > 50% | crash faults | ring / fallback | ✅ `majority_consensus()` (deterministic tie-break) |

## Hybrid PBFT + Raft (frontier 2025–2026)

IEEE/CAA J. Autom. Sinica, July 2025, "Secure Consensus Control on Multi-Agent Systems Based on Improved PBFT and Raft" proposes a **two-tier** scheme:

- **Inter-group** PBFT for leader-identity verification (high security)
- **Intra-group** Raft for log replication (high throughput)
- ECC signing on every replicated log entry

Implication for `hive-swarm`: the current `bft_consensus()` does **not** sign votes. A Byzantine voter could submit two different `proposed_action` strings under the same agent_id and both would be counted (no anti-replay). This is captured as **Finding 22-S1** in `agents/agent_22_bft.md`.

## Semantic-consensus building blocks (LLM-specific)

| Technique | When to use | Implemented? |
|---|---|---|
| **Plurality voting** | discrete labels (sentiment, classification) | ✅ majority |
| **Weighted voting** | agents have differing trust scores (Elo) | ⚠️ partial — gossip uses confidence as weight, but no historical Elo |
| **Token-confidence** | agent emits probability instead of bool | ✅ all protocols use `confidence ∈ [0, 1]` |
| **Embedding-similarity vote** | agents emit free text — cluster by cosine | ❌ not implemented; current code does string-equality on `proposed_action` |
| **Self-consistency / chain-of-thought sampling** | single agent, k samples, majority | n/a (orchestrator-level) |

The single biggest missing piece in `hive-swarm`: **string-equality vote bucketing**. If three coders return:

```
"def add(a,b): return a+b"
"def add(a, b):\n    return a+b"
"def add(a, b): return a + b"
```

Each is a unique vote — the swarm fails to reach consensus despite semantic agreement. Captured as **Finding 17-C2** in `agents/agent_17_consensus_node.md`.

## Tie-break rules (verified against code)

`majority_consensus()` at `hive-swarm/swarm/models/consensus.py:L185-L200`:

```python
ranked = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
```

→ alphabetical tie-break is **deterministic** ✅ but means workers whose action strings start with `[A...]` always win ties over `[Z...]`. This is a soft bias. Recommendation in `agents/agent_24_majority.md`: tie-break by `min(timestamp)` of votes for that action (first proposer wins).

## BFT quorum math — verified

`bft_consensus()` at `consensus.py:L107`:

```python
threshold = math.ceil(len(votes) * quorum_fraction)
```

For `n=3, q=0.67`: `threshold = ceil(3 * 0.67) = ceil(2.01) = 3` → **requires unanimity for 3 voters**, defeating fault tolerance!

For `n=4, q=0.67`: `threshold = ceil(4 * 0.67) = ceil(2.68) = 3` → tolerates 1 Byzantine ✅

This is the classic PBFT trap: with 3 voters, q=0.67 needs unanimity. Either:
- enforce `len(votes) >= 4` when protocol == "bft" (defensive)
- use `floor(2n/3) + 1` (the textbook formula, gives 2 for n=3 → tolerates 1 fault)

Captured as **Finding 22-C1**.

## Convergence / safety properties to test

| Property | Protocol(s) | Test we'd add |
|---|---|---|
| Liveness under f<n/3 faulty | BFT | property-based: random faulty subset → result.failed iff > floor(n/3) faulty |
| Leader uniqueness | Raft | inject 2 queen votes → must pick highest confidence (currently does ✅) |
| Eventual convergence | Gossip | random vote schedule × N rounds → final action stabilises |
| Idempotence | Majority | run consensus twice on same vote set → identical result |

None of these property-based tests exist in `hive-swarm/tests/test_consensus.py` (verified). Captured as **Finding 04-T1** in `agents/agent_04_test_coverage.md`.
