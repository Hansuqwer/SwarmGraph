"""hive-swarm public API surface.

Patched 2026-05-07 by hive orchestrator (objective_hash a3f9c2e1b8d74f06+patch).
See PATCH_REPORT_2026-05-07.md for the full change list.
"""

from .graphs.factory import build_swarm_graph
from .models.agent import (
    AgentSpec,
    AgentState,
    AgentVote,
    ApprovalDecision,  # F-19B (new)
    WorkerResult,
)
from .models.config import SwarmConfig
from .models.consensus import (
    ConsensusResult,
    bft_consensus,
    canonicalize_action,  # F-17A helper
    gossip_consensus,
    majority_consensus,
    raft_consensus,
    run_consensus,
)
from .models.memory import SwarmMemory, SwarmMemoryEntry
from .models.state import SwarmCheckpoint, SwarmState
from .models.task import QueenDirective, SwarmTask
from .models.types import (
    AgentRole,
    AgentStatus,
    ComplexityTier,
    ConsensusProtocol,
    SwarmFailureCause,
    SwarmStatus,
    SwarmStrategy,
    SwarmTopology,
    TaskPriority,
    TaskStatus,
)
from .nodes.checkpointing import (
    FileCheckpointStore,
    InProcessCheckpointStore,
    SwarmRedactingCheckpointer,
)

__all__ = [
    # Config
    "SwarmConfig",
    # State
    "SwarmState",
    "SwarmCheckpoint",
    # Agent models
    "AgentSpec",
    "AgentState",
    "AgentVote",
    "ApprovalDecision",
    "WorkerResult",
    # Task models
    "SwarmTask",
    "QueenDirective",
    # Consensus
    "ConsensusResult",
    "run_consensus",
    "raft_consensus",
    "bft_consensus",
    "gossip_consensus",
    "majority_consensus",
    "canonicalize_action",
    # Memory
    "SwarmMemory",
    "SwarmMemoryEntry",
    # Checkpoint stores
    "InProcessCheckpointStore",
    "FileCheckpointStore",
    "SwarmRedactingCheckpointer",
    # Graph factory
    "build_swarm_graph",
    # Types
    "AgentRole",
    "AgentStatus",
    "SwarmTopology",
    "ConsensusProtocol",
    "SwarmStrategy",
    "SwarmStatus",
    "SwarmFailureCause",
    "TaskStatus",
    "TaskPriority",
    "ComplexityTier",
]

__version__ = "1.1.0-patched"
