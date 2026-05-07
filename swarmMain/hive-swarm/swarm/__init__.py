"""
AGENT 30 — Integration & Final Assembly Agent
Public API surface for the swarm package.
"""
from .graphs.factory import build_swarm_graph
from .models.agent import AgentSpec, AgentState, AgentVote, WorkerResult
from .models.config import SwarmConfig
from .models.consensus import ConsensusResult, run_consensus
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
from .nodes.checkpointing import FileCheckpointStore, InProcessCheckpointStore

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
    "WorkerResult",
    # Task models
    "SwarmTask",
    "QueenDirective",
    # Consensus
    "ConsensusResult",
    "run_consensus",
    # Memory
    "SwarmMemory",
    "SwarmMemoryEntry",
    # Checkpoint stores
    "InProcessCheckpointStore",
    "FileCheckpointStore",
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
