"""SwarmConfig — patched (v4 — adds llm_* fields).

Backwards compatible: every llm_* field has a default that preserves pre-v4
behaviour. SwarmConfig() with no args still ⇒ stub mode, no network calls.

History:
  F-10A: bft_quorum_fraction lower bound tightened to 0.667 (PBFT minimum)
  F-10-T1: memory_namespace charset validator
  F-10-DOC1: raft_queen_authoritative documented
  v4: llm_backend, llm_default_provider, llm_max_tokens, llm_temperature,
      llm_timeout_seconds, llm_include_retrieved_patterns,
      llm_include_objective, llm_role_provider_overrides
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel
from .types import ConsensusProtocol, SwarmStrategy, SwarmTopology


LLMBackend = Literal["stub", "gateway"]


_PROVIDER_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


class SwarmConfig(FrozenModel):
    """Immutable swarm configuration."""

    # ── Topology & agent count ────────────────────────────────────────────
    topology: SwarmTopology = "hierarchical"
    max_agents: int = Field(default=8, ge=1, le=100)
    strategy: SwarmStrategy = "development"

    # ── Consensus ─────────────────────────────────────────────────────────
    consensus_protocol: ConsensusProtocol = "raft"
    bft_quorum_fraction: float = Field(
        default=0.67,
        ge=0.667,
        le=1.0,
        description="PBFT supermajority. Minimum 0.667 to preserve fault tolerance.",
    )
    raft_queen_authoritative: bool = Field(
        default=True,
        description=(
            "Only consumed by the Raft consensus dispatch in run_consensus(). "
            "Has no effect when consensus_protocol != 'raft'."
        ),
    )
    require_min_voters: int = Field(
        default=1,
        ge=1,
        le=100,
        description="F-17B: force HITL when vote_count < this (except authoritative Raft)",
    )

    # ── Anti-drift ────────────────────────────────────────────────────────
    anti_drift_enabled: bool = True
    anti_drift_similarity_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    checkpoint_every_n_tasks: int = Field(default=1, ge=1, le=100)

    # ── 3-Tier routing thresholds ─────────────────────────────────────────
    tier1_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    tier2_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    # ── Memory / SONA ─────────────────────────────────────────────────────
    memory_namespace: str = Field(
        default="default",
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )
    memory_max_entries: int = Field(default=1000, ge=10, le=100_000)
    sona_enabled: bool = True
    sona_min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    # ── HITL ──────────────────────────────────────────────────────────────
    require_approval_above_risk: float = Field(default=0.8, ge=0.0, le=1.0)
    max_iterations: int = Field(default=10, ge=1, le=50)

    # ── v4: LLM dispatch settings ─────────────────────────────────────────
    llm_backend: LLMBackend = Field(
        default="stub",
        description=(
            "Worker LLM backend. 'stub' = deterministic local strings (no network); "
            "'gateway' = route through ai-provider-swarm-gateway adapters. "
            "Override via env: HIVE_SWARM_LLM_BACKEND."
        ),
    )
    llm_default_provider: str = Field(
        default="9router",
        min_length=1,
        max_length=64,
        description=(
            "Provider id for gateway dispatch. Looked up in "
            "ai_provider_swarm_gateway.graph.nodes._get_adapter. "
            "Override via env: HIVE_SWARM_LLM_PROVIDER."
        ),
    )
    llm_max_tokens: int = Field(default=512, ge=1, le=128_000)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    llm_include_retrieved_patterns: bool = Field(
        default=True,
        description="Include SONA-retrieved patterns in the user prompt (F-27A).",
    )
    llm_include_objective: bool = Field(
        default=True,
        description="Include the overall swarm objective alongside the per-task description.",
    )
    llm_role_provider_overrides: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-role provider override, e.g. {'coder': 'openrouter'}. "
            "Roles missing from this dict use llm_default_provider."
        ),
    )

    # ── Schema versioning (F-09B) ─────────────────────────────────────────
    schema_version: int = Field(default=1, ge=1)

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("llm_default_provider")
    @classmethod
    def _provider_charset(cls, v: str) -> str:
        if not _PROVIDER_NAME_RE.match(v):
            raise ValueError(
                "llm_default_provider must match [a-zA-Z0-9_-]+; "
                f"got {v!r}"
            )
        return v

    @field_validator("llm_role_provider_overrides")
    @classmethod
    def _override_keys_and_values_charset(cls, v: dict[str, str]) -> dict[str, str]:
        for role, provider in v.items():
            if not isinstance(role, str) or not isinstance(provider, str):
                raise ValueError(
                    "llm_role_provider_overrides must be dict[str, str]"
                )
            if not _PROVIDER_NAME_RE.match(provider):
                raise ValueError(
                    f"override provider {provider!r} for role {role!r} "
                    "must match [a-zA-Z0-9_-]+"
                )
        return v

    @model_validator(mode="after")
    def _tiers_must_be_ordered(self) -> "SwarmConfig":
        if self.tier1_threshold >= self.tier2_threshold:
            raise ValueError(
                f"tier1_threshold ({self.tier1_threshold}) must be "
                f"< tier2_threshold ({self.tier2_threshold})"
            )
        return self

    @model_validator(mode="after")
    def _bft_quorum_reasonable(self) -> "SwarmConfig":
        if self.consensus_protocol == "bft" and self.bft_quorum_fraction == 1.0:
            raise ValueError(
                "bft_quorum_fraction=1.0 defeats fault tolerance; use < 1.0 for BFT"
            )
        return self

    def complexity_tier(self, score: float) -> str:
        if score < self.tier1_threshold:
            return "tier1_fast"
        elif score < self.tier2_threshold:
            return "tier2_medium"
        return "tier3_swarm"


__all__ = ["SwarmConfig", "LLMBackend"]
