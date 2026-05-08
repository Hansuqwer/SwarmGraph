"""Shared Literal type definitions. Single source of truth.

F-13C: _QUEEN_NODE_NAMES centralised here (was duplicated in factory.py + router.py).
"""
from __future__ import annotations
from typing import Literal

# --- Agent roles ---
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

# --- Swarm topology ---
SwarmTopology = Literal["hierarchical", "mesh", "ring", "star", "adaptive"]

# --- Consensus protocol ---
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
    "approval_replay",          # F-19A: new (single-use guard violation)
    "model_error",
    "split_brain",              # F-21A: new (multiple queens)
    "unknown",
]

# --- Complexity tiers ---
ComplexityTier = Literal["tier1_fast", "tier2_medium", "tier3_swarm"]

# --- History entry kinds ---
HistoryKind = Literal[
    "swarm_init",
    "route",                    # F-14A / F-14-OBS1: distinct from swarm_init
    "task_assigned",
    "worker_result",
    "consensus",
    "consensus_failed",         # F-17C
    "judge",
    "memory_store",
    "memory_retrieve",
    "approval_request",
    "approval_decision",
    "approval_replay_blocked",  # F-19A
    "sona_distill",
    "drift_detected",
    "split_brain_detected",     # F-21A
    "error",
]

# F-13C: single source of truth for queen node names
QUEEN_NODE_NAMES: dict[SwarmTopology, str] = {
    "hierarchical": "hierarchical_queen",
    "mesh": "mesh_queen",
    "ring": "ring_queen",
    "star": "star_queen",
    "adaptive": "adaptive_queen",
}
