"""
AGENT 07 — Agent Model Specialist
AgentSpec, AgentState, AgentVote, WorkerResult — fully typed and hardened.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel, HardenedModel, now_ts, stable_hash
from .types import AgentRole, AgentStatus


# ---------------------------------------------------------------------------
# AgentSpec — who an agent is (immutable identity)
# ---------------------------------------------------------------------------

class AgentSpec(FrozenModel):
    """
    Immutable agent identity record.
    Created at spawn time; never mutated.

    Ruflo equivalent: agent_spawn(type=role, name=agent_id)
    """
    agent_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    role: AgentRole
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("agent_id")
    @classmethod
    def _id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("agent_id must not contain spaces")
        return v

    def spawn_tag(self) -> str:
        """Stable tag for logging and history entries."""
        return f"{self.role}:{self.agent_id}"


# ---------------------------------------------------------------------------
# AgentState — per-agent mutable runtime state (LangGraph sub-state)
# ---------------------------------------------------------------------------

class AgentState(HardenedModel):
    """
    Mutable per-agent state passed to worker LangGraph nodes.
    Each worker receives a copy; results are merged back into SwarmState.
    """
    agent_id: str = Field(..., min_length=1)
    role: AgentRole
    status: AgentStatus = "idle"

    # Input from queen
    assigned_task_id: str | None = None
    task_description: str = ""
    task_context: dict[str, Any] = Field(default_factory=dict)

    # Output produced
    output: str = ""
    output_hash: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Lifecycle
    started_at: float | None = None
    completed_at: float | None = None
    error_message: str = ""

    @model_validator(mode="after")
    def _set_output_hash(self) -> "AgentState":
        if self.output and not self.output_hash:
            self.output_hash = stable_hash(self.output)
        return self

    def mark_started(self) -> None:
        self.status = "working"
        self.started_at = now_ts()

    def mark_done(self, output: str, confidence: float) -> None:
        self.status = "done"
        self.output = output
        self.confidence = confidence
        self.output_hash = stable_hash(output)
        self.completed_at = now_ts()

    def mark_failed(self, reason: str) -> None:
        self.status = "failed"
        self.error_message = reason
        self.completed_at = now_ts()

    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


# ---------------------------------------------------------------------------
# AgentVote — one agent's consensus vote
# ---------------------------------------------------------------------------

class AgentVote(FrozenModel):
    """
    A single agent's vote in a consensus round.
    Immutable after creation — votes cannot be changed post-submission.
    """
    agent_id: str = Field(..., min_length=1)
    agent_role: AgentRole
    proposed_action: str = Field(..., min_length=1, max_length=2048)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=1024)
    output_hash: str = ""
    timestamp: float = Field(default_factory=now_ts)

    @field_validator("proposed_action")
    @classmethod
    def _action_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("proposed_action must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# WorkerResult — structured output from a completed worker node
# ---------------------------------------------------------------------------

class WorkerResult(FrozenModel):
    """
    The final output record from one worker agent node.
    Collected into SwarmState.worker_results for consensus aggregation.
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
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_success_consistency(self) -> "WorkerResult":
        if self.success and not self.output.strip():
            raise ValueError("Successful WorkerResult must have non-empty output")
        if not self.success and not self.error_message.strip():
            raise ValueError("Failed WorkerResult must have non-empty error_message")
        return self

    @model_validator(mode="after")
    def _compute_output_hash(self) -> "WorkerResult":
        if self.output and not self.output_hash:
            object.__setattr__(self, "output_hash", stable_hash(self.output))
        return self

    def to_vote(self) -> AgentVote:
        """Convert this result to an AgentVote for consensus aggregation."""
        return AgentVote(
            agent_id=self.agent_id,
            agent_role=self.agent_role,
            proposed_action=self.output or "NO_OUTPUT",
            confidence=self.confidence if self.success else 0.0,
            output_hash=self.output_hash,
        )
