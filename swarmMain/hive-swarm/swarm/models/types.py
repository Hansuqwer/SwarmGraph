"""
AGENT 06 + 07 + 08 + 09 + 10 — Shared Literal type definitions.
Single source of truth for all discriminated union keys.
"""
from __future__ import annotations
from typing import Literal

# --- Agent roles (Ruflo: coder, tester, reviewer, architect ...) ---
AgentRole = Literal[
    "queen",
    "coordinator",
    "coder",
    "tester",
    "reviewer",
    "researcher",
    "architect",
    "security",
    "optimizer",
    "documenter",
]

# --- Agent lifecycle ---
AgentStatus = Literal["idle", "working", "blocked", "done", "failed"]

# --- Task lifecycle ---
TaskStatus = Literal[
    "pending", "assigned", "running", "completed", "failed", "cancelled"
]
TaskPriority = Literal["low", "medium", "high", "critical"]

# --- Swarm topology (Ruflo: hierarchical, mesh, ring, star, adaptive) ---
SwarmTopology = Literal["hierarchical", "mesh", "ring", "star", "adaptive"]

# --- Consensus protocol (Ruflo: raft, bft, gossip, crdt) ---
ConsensusProtocol = Literal["raft", "bft", "gossip", "majority"]

# --- Swarm strategy ---
SwarmStrategy = Literal["development", "research", "security", "specialized", "analysis"]

# --- Top-level swarm lifecycle ---
SwarmStatus = Literal[
    "initializing",
    "routing",
    "decomposing",
    "executing",
    "voting",
    "judging",
    "awaiting_approval",
    "distilling",
    "completed",
    "failed",
    "denied",
    "drifted",
]

# --- Failure causes ---
SwarmFailureCause = Literal[
    "consensus_failed",
    "quorum_not_reached",
    "objective_drift",
    "all_workers_failed",
    "max_iterations_exceeded",
    "approval_denied",
    "model_error",
    "unknown",
]

# --- Complexity tiers ---
ComplexityTier = Literal["tier1_fast", "tier2_medium", "tier3_swarm"]

# --- History entry kinds ---
HistoryKind = Literal[
    "swarm_init",
    "task_assigned",
    "worker_result",
    "consensus",
    "judge",
    "memory_store",
    "memory_retrieve",
    "approval_request",
    "approval_decision",
    "sona_distill",
    "drift_detected",
    "error",
]
