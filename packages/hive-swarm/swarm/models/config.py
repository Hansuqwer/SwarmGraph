"""SwarmConfig — patched (v8: audit signing + streaming HITL).

History (v4–v7.1) preserved.

v8 NEW fields:
  - audit_signing_enabled: bool                  # default False (back-compat)
  - audit_secret_env: str                        # env var holding HMAC secret
  - audit_log_path: str                          # optional JSONL path; "{tenant}" placeholder
  - audit_kinds: tuple[str, ...]                 # which event kinds to sign
  - streaming_guard_patterns: list[str]          # regex denylist for streaming output
  - streaming_max_output_chars: int              # per-worker stream length cap
  - streaming_hitl_action_default: Literal       # default action on guard trigger
  - streaming_guard_check_every_n_chunks: int    # throttle the regex eval

All defaults preserve v7.1 behaviour.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel
from .types import ConsensusProtocol, SwarmStrategy, SwarmTopology


LLMBackend = Literal["stub", "gateway"]
AntiDriftMode = Literal["off", "keyword", "embedding"]
StreamingHITLAction = Literal["abort", "continue", "accept_partial"]

_PROVIDER_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-/:\.]+$")
_ENV_VAR_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

_DEFAULT_AUDIT_KINDS: tuple[str, ...] = (
    "consensus_result",
    "approval_decision",
    "worker_result",
    "stream_hitl_decision",
)


class SwarmConfig(FrozenModel):
    """Immutable swarm configuration."""

    # ── Topology & agent count ────────────────────────────────────────────
    topology: SwarmTopology = "hierarchical"
    max_agents: int = Field(default=8, ge=1, le=100)
    strategy: SwarmStrategy = "development"

    # ── Consensus ─────────────────────────────────────────────────────────
    consensus_protocol: ConsensusProtocol = "raft"
    bft_quorum_fraction: float = Field(default=0.67, ge=0.667, le=1.0)
    raft_queen_authoritative: bool = True
    require_min_voters: int = Field(default=1, ge=1, le=100)

    # ── Anti-drift ────────────────────────────────────────────────────────
    anti_drift_enabled: bool = True
    anti_drift_mode: AntiDriftMode = "keyword"
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
    llm_backend: LLMBackend = "stub"
    llm_default_provider: str = Field(default="9router", min_length=1, max_length=64)
    llm_default_model: str = Field(default="", max_length=256)
    llm_max_tokens: int = Field(default=512, ge=1, le=128_000)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    llm_include_retrieved_patterns: bool = True
    llm_include_objective: bool = True
    llm_role_provider_overrides: dict[str, str] = Field(default_factory=dict)
    llm_role_model_overrides: dict[str, str] = Field(default_factory=dict)
    llm_stream_enabled: bool = False
    cost_tracking_enabled: bool = True

    # ── v8: Audit log signing ─────────────────────────────────────────────
    audit_signing_enabled: bool = Field(
        default=False,
        description=(
            "Enable HMAC-SHA256 signing of consensus/approval/worker records. "
            "Records are appended to SwarmState.audit_records and optionally "
            "to a JSONL file (audit_log_path)."
        ),
    )
    audit_secret_env: str = Field(
        default="HIVE_SWARM_AUDIT_SECRET",
        max_length=64,
        description=(
            "Env var holding the HMAC secret. Required when audit_signing_enabled. "
            "Tests can use any non-empty value; production should use 32+ random bytes."
        ),
    )
    audit_log_path: str = Field(
        default="",
        max_length=512,
        description=(
            "Optional JSONL path for persistent audit log. May contain '{tenant}' "
            "and '{swarm_id}' placeholders. Empty = in-process records only."
        ),
    )
    audit_kinds: tuple[str, ...] = Field(
        default=_DEFAULT_AUDIT_KINDS,
        description="Which event kinds to sign + record. Empty = sign nothing.",
    )

    # ── v8: Streaming HITL ────────────────────────────────────────────────
    streaming_guard_patterns: list[str] = Field(
        default_factory=list,
        max_length=64,
        description=(
            "Regex patterns matched against accumulated streamed output. "
            "First match raises StreamingHITLInterrupt with the matched text."
        ),
    )
    streaming_max_output_chars: int = Field(
        default=16384,
        ge=128,
        le=10_000_000,
        description=(
            "Per-worker streaming output cap. Beyond this, dispatcher raises "
            "StreamingHITLInterrupt(reason='max_chars_exceeded')."
        ),
    )
    streaming_hitl_action_default: StreamingHITLAction = Field(
        default="abort",
        description=(
            "What to do when no operator is available (non-TTY, no resume hook). "
            "abort = treat as worker failure; continue = ignore guard; "
            "accept_partial = use accumulated output as final."
        ),
    )
    streaming_guard_check_every_n_chunks: int = Field(
        default=4,
        ge=1,
        le=1000,
        description=(
            "Throttle: only run regex match every N chunks (since checking on "
            "every chunk is wasteful for short tokens)."
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

    @field_validator("audit_secret_env")
    @classmethod
    def _audit_env_var_format(cls, v: str) -> str:
        # Only enforce when non-empty (default value passes)
        if v and not _ENV_VAR_NAME_RE.match(v):
            raise ValueError(
                f"audit_secret_env must be a valid env var name "
                f"[A-Z_][A-Z0-9_]*; got {v!r}"
            )
        return v

    @field_validator("streaming_guard_patterns")
    @classmethod
    def _streaming_patterns_compile(cls, v: list[str]) -> list[str]:
        """Compile each pattern eagerly to catch invalid regex at config time."""
        for pat in v:
            if not isinstance(pat, str):
                raise ValueError("streaming_guard_patterns must be list[str]")
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"invalid regex pattern {pat!r}: {e}")
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

    @model_validator(mode="after")
    def _audit_kinds_known(self) -> "SwarmConfig":
        valid = {
            "consensus_result", "approval_decision", "worker_result",
            "stream_hitl_decision", "swarm_init", "swarm_complete",
        }
        bad = set(self.audit_kinds) - valid
        if bad:
            raise ValueError(
                f"audit_kinds contains unknown kinds: {sorted(bad)}; "
                f"valid: {sorted(valid)}"
            )
        return self

    def complexity_tier(self, score: float) -> str:
        if score < self.tier1_threshold:
            return "tier1_fast"
        elif score < self.tier2_threshold:
            return "tier2_medium"
        return "tier3_swarm"

    def resolve_audit_log_path(self, *, swarm_id: str, tenant_id: str = "") -> str:
        """Substitute {tenant} and {swarm_id} placeholders in audit_log_path."""
        if not self.audit_log_path:
            return ""
        return (
            self.audit_log_path
            .replace("{tenant}", tenant_id or "default")
            .replace("{swarm_id}", swarm_id)
        )


__all__ = ["SwarmConfig", "LLMBackend", "AntiDriftMode", "StreamingHITLAction"]
