"""SwarmConfig — patched (v5 — adds llm_role_model_overrides).

History preserved:
  F-10A, F-10-T1, F-10-DOC1, v4 llm_* fields.

v5 NEW field:
  llm_role_model_overrides: dict[str, str]   # {"coder": "anthropic/claude-opus-4-7"}

Backwards compatible: all new fields default to current behaviour.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel
from .types import ConsensusProtocol, SwarmStrategy, SwarmTopology


LLMBackend = Literal["stub", "gateway"]

_PROVIDER_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
# Model ids commonly include slashes (provider/model), colons (suffixes), dots
_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-/:\.]+$")


class SwarmConfig(FrozenModel):
    """Immutable swarm configuration."""

    # ── Topology & agent count ────────────────────────────────────────────
    topology: SwarmTopology = "hierarchical"
    max_agents: int = Field(default=8, ge=1, le=100)
    strategy: SwarmStrategy = "development"

    # ── Consensus ─────────────────────────────────────────────────────────
    consensus_protocol: ConsensusProtocol = "raft"
    bft_quorum_fraction: float = Field(
        default=0.67, ge=0.667, le=1.0,
        description="PBFT supermajority. Minimum 0.667 to preserve fault tolerance.",
    )
    raft_queen_authoritative: bool = Field(
        default=True,
        description="Only consumed by Raft consensus dispatch.",
    )
    require_min_voters: int = Field(default=1, ge=1, le=100)

    # ── Anti-drift ────────────────────────────────────────────────────────
    anti_drift_enabled: bool = True
    anti_drift_similarity_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    checkpoint_every_n_tasks: int = Field(default=1, ge=1, le=100)

    # ── 3-Tier routing thresholds ─────────────────────────────────────────
    tier1_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    tier2_threshold: float = Field(default=0.50, ge=0.0, le=1.0)

    # ── Memory / SONA ─────────────────────────────────────────────────────
    memory_namespace: str = Field(
        default="default", min_length=1, max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )
    memory_max_entries: int = Field(default=1000, ge=10, le=100_000)
    sona_enabled: bool = True
    sona_min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    # ── HITL ──────────────────────────────────────────────────────────────
    require_approval_above_risk: float = Field(default=0.8, ge=0.0, le=1.0)
    max_iterations: int = Field(default=10, ge=1, le=50)

    # ── LLM dispatch ──────────────────────────────────────────────────────
    llm_backend: LLMBackend = Field(default="stub")
    llm_default_provider: str = Field(default="9router", min_length=1, max_length=64)
    llm_default_model: str = Field(
        default="", max_length=256,
        description="Default model id. Empty → adapter default. Override via env HIVE_SWARM_LLM_MODEL.",
    )
    llm_max_tokens: int = Field(default=512, ge=1, le=128_000)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    llm_include_retrieved_patterns: bool = Field(default=True)
    llm_include_objective: bool = Field(default=True)
    llm_role_provider_overrides: dict[str, str] = Field(default_factory=dict)

    # v5 NEW
    llm_role_model_overrides: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-role model_id override. Example: "
            "{'coder': 'anthropic/claude-opus-4-7', 'tester': 'openai/gpt-4o-mini'}. "
            "Roles missing from this dict use llm_default_model (or adapter default)."
        ),
    )

    # ── Schema versioning (F-09B) ─────────────────────────────────────────
    schema_version: int = Field(default=1, ge=1)

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("llm_default_provider")
    @classmethod
    def _provider_charset(cls, v: str) -> str:
        if not _PROVIDER_NAME_RE.match(v):
            raise ValueError(f"llm_default_provider must match [a-zA-Z0-9_-]+; got {v!r}")
        return v

    @field_validator("llm_default_model")
    @classmethod
    def _default_model_charset(cls, v: str) -> str:
        if v and not _MODEL_NAME_RE.match(v):
            raise ValueError(f"llm_default_model must match [a-zA-Z0-9_\\-/:.]+; got {v!r}")
        return v

    @field_validator("llm_role_provider_overrides")
    @classmethod
    def _role_provider_charset(cls, v: dict[str, str]) -> dict[str, str]:
        for role, provider in v.items():
            if not isinstance(role, str) or not isinstance(provider, str):
                raise ValueError("llm_role_provider_overrides must be dict[str, str]")
            if not _PROVIDER_NAME_RE.match(provider):
                raise ValueError(
                    f"override provider {provider!r} for role {role!r} "
                    "must match [a-zA-Z0-9_-]+"
                )
        return v

    @field_validator("llm_role_model_overrides")
    @classmethod
    def _role_model_charset(cls, v: dict[str, str]) -> dict[str, str]:
        for role, model_id in v.items():
            if not isinstance(role, str) or not isinstance(model_id, str):
                raise ValueError("llm_role_model_overrides must be dict[str, str]")
            if model_id and not _MODEL_NAME_RE.match(model_id):
                raise ValueError(
                    f"override model {model_id!r} for role {role!r} "
                    "must match [a-zA-Z0-9_\\-/:.]+"
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
