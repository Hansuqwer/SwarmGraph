"""Agent models — patched (v5).

History:
  F-07A: _compute_output_hash always recomputes
  F-07-CORR2: mark_done after fail raises
  F-07-CORR3 (your local fix): WorkerResult.to_vote truncates long outputs
                                while preserving output_hash
  F-19B: ApprovalDecision typed model
  F-22B (foundation): AgentVote signature/nonce/round_id fields
  v5: TokenUsage model + WorkerResult.usage: TokenUsage | None
"""
from __future__ import annotations

import secrets
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from .base import FrozenModel, HardenedModel, monotonic_ts, now_ts, stable_hash
from .types import AgentRole, AgentStatus


# ── TokenUsage (v5) ──────────────────────────────────────────────────────

class TokenUsage(FrozenModel):
    """Token counts from a model gateway call. All fields ≥ 0 (append-only)."""
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    model_id_used: str = Field(default="", max_length=256)
    finish_reason: str = Field(default="", max_length=64)
    provider_id: str = Field(default="", max_length=64)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ── AgentSpec — immutable identity ─────────────────────────────────────────

class AgentSpec(FrozenModel):
    """Immutable agent identity record."""
    agent_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    role: AgentRole
    capabilities: list[str] = Field(default_factory=list, max_length=64)
    metadata: dict[str, str] = Field(default_factory=dict, max_length=64)

    @field_validator("agent_id")
    @classmethod
    def _id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("agent_id must not contain spaces")
        return v

    def spawn_tag(self) -> str:
        return f"{self.role}:{self.agent_id}"


# ── AgentState ────────────────────────────────────────────────────────────

class AgentState(HardenedModel):
    """Mutable per-agent state passed to worker LangGraph nodes."""
    agent_id: str = Field(..., min_length=1)
    role: AgentRole
    status: AgentStatus = "idle"

    assigned_task_id: str | None = None
    task_description: str = ""
    task_context: dict[str, Any] = Field(default_factory=dict)

    output: str = ""
    output_hash: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    started_at: float | None = None
    completed_at: float | None = None
    started_monotonic: float | None = None
    completed_monotonic: float | None = None
    error_message: str = ""

    @model_validator(mode="after")
    def _set_output_hash(self) -> "AgentState":
        if self.output and not self.output_hash:
            self.output_hash = stable_hash(self.output)
        return self

    def mark_started(self) -> None:
        self.status = "working"
        self.started_at = now_ts()
        self.started_monotonic = monotonic_ts()

    def mark_done(self, output: str, confidence: float) -> None:
        if self.status == "failed":
            raise RuntimeError(
                f"Cannot mark_done agent {self.agent_id!r} that already failed"
            )
        self.status = "done"
        self.output = output
        self.confidence = confidence
        self.output_hash = stable_hash(output)
        self.completed_at = now_ts()
        self.completed_monotonic = monotonic_ts()

    def mark_failed(self, reason: str) -> None:
        self.status = "failed"
        self.error_message = reason
        self.completed_at = now_ts()
        self.completed_monotonic = monotonic_ts()

    def duration_seconds(self) -> float | None:
        if self.started_monotonic is not None and self.completed_monotonic is not None:
            return self.completed_monotonic - self.started_monotonic
        if self.started_at and self.completed_at:
            return max(0.0, self.completed_at - self.started_at)
        return None


# ── AgentVote ────────────────────────────────────────────────────────────

class AgentVote(FrozenModel):
    """A single agent's immutable vote.

    F-22B foundation: optional cryptographic fields (signing logic deferred).
    """
    agent_id: str = Field(..., min_length=1)
    agent_role: AgentRole
    proposed_action: str = Field(..., min_length=1, max_length=2048)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=1024)
    output_hash: str = ""
    timestamp: float = Field(default_factory=now_ts)

    nonce: str = Field(default_factory=lambda: secrets.token_hex(16), max_length=64)
    round_id: str = Field(default="", max_length=64)
    signature: str | None = None

    @field_validator("proposed_action")
    @classmethod
    def _action_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("proposed_action must not be blank")
        return v.strip()


# ── WorkerResult (v5) ────────────────────────────────────────────────────

_VOTE_ACTION_MAX = 2048


class WorkerResult(FrozenModel):
    """Frozen result record from one worker.

    v5: gains `usage: TokenUsage | None` populated by gateway-mode workers.
        Stub-mode workers leave it None.
    """
    agent_id: str = Field(..., min_length=1)
    agent_role: AgentRole
    task_id: str = Field(..., min_length=1)

    success: bool
    output: str = ""
    output_hash: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    error_message: str = ""
    duration_seconds: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=32)

    # v5
    usage: TokenUsage | None = None

    @model_validator(mode="after")
    def _validate_success_consistency(self) -> "WorkerResult":
        if self.success and not self.output.strip():
            raise ValueError("Successful WorkerResult must have non-empty output")
        if not self.success and not self.error_message.strip():
            raise ValueError("Failed WorkerResult must have non-empty error_message")
        return self

    @model_validator(mode="after")
    def _compute_output_hash(self) -> "WorkerResult":
        # F-07A: ALWAYS recompute
        if self.output:
            object.__setattr__(self, "output_hash", stable_hash(self.output))
        return self

    def to_vote(self, *, round_id: str = "") -> AgentVote:
        """Convert to AgentVote.

        F-07-CORR3: long LLM outputs (real gateway path) routinely exceed
        AgentVote.proposed_action max_length=2048. Truncate while preserving
        output_hash so consensus.canonicalize_action still buckets correctly
        (hash equality is preserved across the truncation).
        """
        full = self.output or "NO_OUTPUT"
        truncated = full[:_VOTE_ACTION_MAX] if len(full) > _VOTE_ACTION_MAX else full
        return AgentVote(
            agent_id=self.agent_id,
            agent_role=self.agent_role,
            proposed_action=truncated,
            confidence=self.confidence if self.success else 0.0,
            output_hash=self.output_hash,
            round_id=round_id,
        )


# ── ApprovalDecision (F-19B) ─────────────────────────────────────────────

class ApprovalDecision(FrozenModel):
    """Strict shape for HITL resume payload."""
    decision: Literal["approve", "deny"]
    reviewer_id: str = Field(..., min_length=1, max_length=128)
    decision_token: str = Field(..., min_length=8, max_length=64)
    reason: str = Field(default="", max_length=1024)
    decided_at: float = Field(default_factory=now_ts)


__all__ = [
    "TokenUsage",
    "AgentSpec",
    "AgentState",
    "AgentVote",
    "ApprovalDecision",
    "WorkerResult",
]
