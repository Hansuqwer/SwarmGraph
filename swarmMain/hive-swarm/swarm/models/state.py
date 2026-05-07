"""
AGENT 09 — State Model Specialist
AGENT 12 — Validator Specialist
AGENT 05 — Risk & Drift Control

SwarmState — the canonical LangGraph shared state.
SwarmCheckpoint — serializable snapshot for persistence.
"""
from __future__ import annotations

import time
from typing import Any

from pydantic import Field, field_validator, model_validator

from .agent import AgentSpec, AgentVote, WorkerResult
from .base import HardenedModel, now_ts, stable_hash
from .config import SwarmConfig
from .consensus import ConsensusResult
from .memory import SwarmMemory
from .task import SwarmTask
from .types import (
    ComplexityTier,
    HistoryKind,
    SwarmFailureCause,
    SwarmStatus,
    SwarmTopology,
)

# ── Bounds (Agent 12 — Validator Specialist) ─────────────────────────────────
_MAX_HISTORY: int = 500
_MAX_ERRORS: int = 100
_MAX_AGENTS: int = 100


# ---------------------------------------------------------------------------
# SwarmState — top-level LangGraph state
# ---------------------------------------------------------------------------

class SwarmState(HardenedModel):
    """
    The single, canonical shared state for the entire swarm workflow.

    Maps Ruflo concepts:
      swarm_id         ↔ Ruflo session ID
      objective        ↔ swarm start --objective "..."
      objective_hash   ↔ anti-drift reference hash
      topology         ↔ swarm init --topology hierarchical
      agents           ↔ agent pool (agent spawn)
      tasks            ↔ task queue
      memory           ↔ AgentDB / HNSW memory layer
      consensus_result ↔ Raft/BFT/Gossip output
      sona_*           ↔ SONA self-learning state

    Anti-drift enforced by Agent 05 (model_validator):
      Every state transition checks that the objective_hash is preserved.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    swarm_id: str = Field(..., min_length=1, max_length=128)
    objective: str = Field(..., min_length=1, max_length=8192)
    objective_hash: str = Field(default="")   # set by validator

    # ── Configuration ─────────────────────────────────────────────────────────
    config: SwarmConfig

    # ── Agent pool ───────────────────────────────────────────────────────────
    agents: list[AgentSpec] = Field(default_factory=list)

    # ── Task management ──────────────────────────────────────────────────────
    tasks: list[SwarmTask] = Field(default_factory=list)
    current_task_id: str | None = None
    completed_task_ids: list[str] = Field(default_factory=list)

    # ── Routing ──────────────────────────────────────────────────────────────
    complexity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    complexity_tier: ComplexityTier = "tier3_swarm"

    # ── Consensus ────────────────────────────────────────────────────────────
    pending_votes: list[AgentVote] = Field(default_factory=list)
    consensus_result: ConsensusResult | None = None

    # ── Worker results ────────────────────────────────────────────────────────
    worker_results: list[WorkerResult] = Field(default_factory=list)
    latest_output: str = ""
    latest_output_hash: str = ""
    final_output: str = ""

    # ── Memory / SONA ─────────────────────────────────────────────────────────
    memory: SwarmMemory = Field(default_factory=SwarmMemory)
    sona_distilled: bool = False
    sona_cycle_count: int = Field(default=0, ge=0)

    # ── Workflow status ───────────────────────────────────────────────────────
    status: SwarmStatus = "initializing"
    failure_cause: SwarmFailureCause | None = None
    iteration: int = Field(default=0, ge=0)

    # ── Bounded lists ────────────────────────────────────────────────────────
    history: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: float = Field(default_factory=now_ts)
    updated_at: float = Field(default_factory=now_ts)

    # =========================================================================
    # AGENT 12 — Validators
    # =========================================================================

    @field_validator("swarm_id")
    @classmethod
    def _id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("swarm_id must not contain spaces")
        return v

    @field_validator("agents")
    @classmethod
    def _agents_bounded(cls, v: list[AgentSpec]) -> list[AgentSpec]:
        if len(v) > _MAX_AGENTS:
            raise ValueError(f"agents list exceeds maximum of {_MAX_AGENTS}")
        return v

    @model_validator(mode="after")
    def _auto_objective_hash(self) -> "SwarmState":
        """AGENT 12: Auto-compute objective hash for anti-drift (Agent 05)."""
        if not self.objective_hash:
            self.objective_hash = stable_hash(self.objective)
        return self

    @model_validator(mode="after")
    def _cap_lists(self) -> "SwarmState":
        """AGENT 12: Enforce bounded lists (prevents memory exhaustion)."""
        if len(self.history) > _MAX_HISTORY:
            self.history = self.history[:1] + self.history[-(_MAX_HISTORY - 1):]
        if len(self.errors) > _MAX_ERRORS:
            self.errors = self.errors[-_MAX_ERRORS:]
        return self

    @model_validator(mode="after")
    def _agent_count_le_config(self) -> "SwarmState":
        """AGENT 12: agents cannot exceed config.max_agents."""
        if len(self.agents) > self.config.max_agents:
            raise ValueError(
                f"agents count ({len(self.agents)}) exceeds "
                f"config.max_agents ({self.config.max_agents})"
            )
        return self

    # =========================================================================
    # AGENT 05 — Anti-Drift helpers
    # =========================================================================

    def check_drift(self, candidate_output: str) -> bool:
        """
        Returns True if the candidate_output appears to address the objective.
        Keyword overlap heuristic — replace with embedding similarity in production.
        Ruflo: 'hierarchical coordinators validate outputs against original goals'
        """
        if not self.config.anti_drift_enabled:
            return True
        obj_tokens = set(self.objective.lower().split())
        out_tokens = set(candidate_output.lower().split())
        if not obj_tokens:
            return True
        overlap = len(obj_tokens & out_tokens) / len(obj_tokens)
        return overlap >= self.config.anti_drift_similarity_threshold

    def assert_no_drift(self, candidate_output: str) -> None:
        """Raise ValueError if drift is detected. Called in judge_node."""
        if not self.check_drift(candidate_output):
            self.status = "drifted"
            self.failure_cause = "objective_drift"
            raise ValueError(
                f"Anti-drift violation: output does not satisfy objective "
                f"(hash={self.objective_hash})"
            )

    # =========================================================================
    # Mutation helpers
    # =========================================================================

    def touch(self) -> None:
        self.updated_at = now_ts()

    def add_error(self, msg: str) -> None:
        self.errors = (self.errors + [msg])[-_MAX_ERRORS:]

    def append_history(self, kind: HistoryKind, payload: dict[str, Any]) -> None:
        entry: dict[str, Any] = {"kind": kind, "ts": now_ts(), **payload}
        new_history = self.history + [entry]
        if len(new_history) > _MAX_HISTORY:
            new_history = new_history[:1] + new_history[-(_MAX_HISTORY - 1):]
        self.history = new_history

    def get_pending_tasks(self) -> list[SwarmTask]:
        done_ids = set(self.completed_task_ids)
        return [t for t in self.tasks if t.is_ready(done_ids) and t.status == "pending"]

    def mark_task_complete(self, task_id: str, result: str) -> None:
        for task in self.tasks:
            if task.task_id == task_id:
                task.complete(result)
                if task_id not in self.completed_task_ids:
                    self.completed_task_ids = self.completed_task_ids + [task_id]
                break

    def register_agent(self, spec: AgentSpec) -> None:
        if len(self.agents) >= self.config.max_agents:
            raise ValueError(f"Cannot register more than {self.config.max_agents} agents")
        self.agents = self.agents + [spec]

    def collect_vote(self, vote: AgentVote) -> None:
        self.pending_votes = self.pending_votes + [vote]

    def record_worker_result(self, result: WorkerResult) -> None:
        self.worker_results = self.worker_results + [result]
        if result.success:
            self.latest_output = result.output
            self.latest_output_hash = result.output_hash

    def increment_sona(self) -> None:
        self.sona_cycle_count += 1
        self.sona_distilled = True

    def fail(self, cause: SwarmFailureCause, reason: str = "") -> None:
        self.status = "failed"
        self.failure_cause = cause
        if reason:
            self.add_error(reason)

    def to_json_dict(self) -> dict[str, Any]:
        """Full JSON-safe dict for LangGraph state and checkpoint storage."""
        return self.model_dump(mode="json")

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "SwarmState":
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# SwarmCheckpoint — serializable snapshot
# ---------------------------------------------------------------------------

class SwarmCheckpoint(HardenedModel):
    """
    A serializable point-in-time snapshot of SwarmState.
    Written by checkpointing nodes; read for replay and resume.
    """
    checkpoint_id: str = Field(..., min_length=1)
    swarm_id: str
    objective_hash: str
    state_snapshot: dict[str, Any]    # SwarmState.model_dump(mode='json')
    created_at: float = Field(default_factory=now_ts)
    iteration: int = Field(ge=0, default=0)
    status_at_checkpoint: SwarmStatus = "initializing"

    @classmethod
    def from_state(cls, state: SwarmState, checkpoint_id: str) -> "SwarmCheckpoint":
        return cls(
            checkpoint_id=checkpoint_id,
            swarm_id=state.swarm_id,
            objective_hash=state.objective_hash,
            state_snapshot=state.to_json_dict(),
            iteration=state.iteration,
            status_at_checkpoint=state.status,
        )

    def restore(self) -> SwarmState:
        """Restore a SwarmState from this checkpoint."""
        return SwarmState.from_json_dict(self.state_snapshot)
