"""
AGENT 10 — Config Model Specialist
SwarmConfig — frozen, validated, routing thresholds, consensus tuning.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from .base import FrozenModel
from .types import ConsensusProtocol, SwarmStrategy, SwarmTopology


class SwarmConfig(FrozenModel):
    """
    Immutable swarm configuration.
    Frozen after creation — validated at construction, never mutated.
    Ruflo equivalent: swarm_init(topology=..., maxAgents=..., strategy=...)

    Consensus Decisions (Raft — hierarchical design):
      - Default topology: hierarchical (recommended for coding swarms)
      - Default consensus: raft (queen has authoritative state)
      - Anti-drift: enabled by default
      - SONA: enabled by default
    """

    # --- Topology & agent count ---
    topology: SwarmTopology = "hierarchical"
    max_agents: int = Field(default=8, ge=1, le=100)
    strategy: SwarmStrategy = "development"

    # --- Consensus ---
    consensus_protocol: ConsensusProtocol = "raft"
    bft_quorum_fraction: float = Field(default=0.67, ge=0.51, le=1.0)
    raft_queen_authoritative: bool = True

    # --- Anti-drift ---
    anti_drift_enabled: bool = True
    anti_drift_similarity_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    checkpoint_every_n_tasks: int = Field(default=1, ge=1, le=100)

    # --- 3-Tier routing thresholds (Ruflo: ADR-026) ---
    tier1_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    tier2_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    # --- Memory / SONA ---
    memory_namespace: str = Field(default="default", min_length=1, max_length=64)
    memory_max_entries: int = Field(default=1000, ge=10, le=100_000)
    sona_enabled: bool = True
    sona_min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    # --- Human-in-the-loop ---
    require_approval_above_risk: float = Field(default=0.8, ge=0.0, le=1.0)
    max_iterations: int = Field(default=10, ge=1, le=50)

    # --- Validation ---
    @model_validator(mode="after")
    def _tiers_must_be_ordered(self) -> "SwarmConfig":
        """tier1 < tier2 < 1.0 (BFT decision: threshold ordering is a correctness constraint)."""
        if self.tier1_threshold >= self.tier2_threshold:
            raise ValueError(
                f"tier1_threshold ({self.tier1_threshold}) must be "
                f"< tier2_threshold ({self.tier2_threshold})"
            )
        return self

    @model_validator(mode="after")
    def _bft_quorum_reasonable(self) -> "SwarmConfig":
        """BFT quorum must allow at least 1 faulty agent when using BFT consensus."""
        if self.consensus_protocol == "bft" and self.bft_quorum_fraction == 1.0:
            raise ValueError(
                "bft_quorum_fraction=1.0 defeats fault tolerance; use < 1.0 for BFT"
            )
        return self

    def complexity_tier(self, score: float) -> str:
        """Map a [0,1] complexity score to a routing tier name."""
        if score < self.tier1_threshold:
            return "tier1_fast"
        elif score < self.tier2_threshold:
            return "tier2_medium"
        return "tier3_swarm"
