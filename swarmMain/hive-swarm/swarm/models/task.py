"""
AGENT 08 — Task Model Specialist
SwarmTask, QueenDirective — with dependency graph, priority ordering, invariants.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel, HardenedModel, now_ts, stable_hash
from .types import AgentRole, TaskPriority, TaskStatus


# ---------------------------------------------------------------------------
# SwarmTask — a unit of decomposed work
# ---------------------------------------------------------------------------

class SwarmTask(HardenedModel):
    """
    One atomic unit of work within a swarm execution.

    Ruflo equivalent: task create --type implementation --description "..."
    """
    task_id: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=4096)
    priority: TaskPriority = "medium"
    status: TaskStatus = "pending"
    assigned_to: str | None = None         # agent_id
    required_role: AgentRole | None = None  # restrict which roles may claim

    # Dependencies (must complete before this task can run)
    depends_on: list[str] = Field(default_factory=list)   # task_ids

    # Outputs
    result_summary: str = ""
    result_hash: str = ""

    # Metadata
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=now_ts)
    started_at: float | None = None
    completed_at: float | None = None
    attempts: int = Field(default=0, ge=0, le=10)

    @field_validator("task_id")
    @classmethod
    def _id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("task_id must not contain spaces")
        return v

    @field_validator("depends_on")
    @classmethod
    def _no_self_dep(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))  # deduplicate, preserve order

    @model_validator(mode="after")
    def _compute_result_hash(self) -> "SwarmTask":
        if self.result_summary and not self.result_hash:
            self.result_hash = stable_hash(self.result_summary)
        return self

    # --- Lifecycle helpers ---

    def assign(self, agent_id: str) -> None:
        if self.status != "pending":
            raise ValueError(f"Cannot assign task in status {self.status!r}")
        self.status = "assigned"
        self.assigned_to = agent_id

    def start(self) -> None:
        if self.status not in ("assigned", "pending"):
            raise ValueError(f"Cannot start task in status {self.status!r}")
        self.status = "running"
        self.started_at = now_ts()
        self.attempts += 1

    def complete(self, result: str) -> None:
        self.status = "completed"
        self.result_summary = result
        self.result_hash = stable_hash(result)
        self.completed_at = now_ts()

    def fail(self, reason: str = "") -> None:
        self.status = "failed"
        self.result_summary = reason
        self.completed_at = now_ts()

    def cancel(self) -> None:
        self.status = "cancelled"
        self.completed_at = now_ts()

    def is_ready(self, completed_task_ids: set[str]) -> bool:
        """True when all dependencies have completed."""
        return all(dep in completed_task_ids for dep in self.depends_on)

    def priority_value(self) -> int:
        """Numeric priority for sorting (higher = more urgent)."""
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[self.priority]


# ---------------------------------------------------------------------------
# QueenDirective — instruction issued by the queen node to workers
# ---------------------------------------------------------------------------

class QueenDirective(FrozenModel):
    """
    Immutable instruction from the queen node to one worker agent.
    Created inside queen_node(), dispatched via Send().
    """
    directive_id: str = Field(..., min_length=1)
    task: SwarmTask
    assigned_agent_id: str = Field(..., min_length=1)
    assigned_role: AgentRole
    objective_hash: str = Field(..., min_length=1)   # anti-drift reference
    shared_context: dict[str, Any] = Field(default_factory=dict)
    issued_at: float = Field(default_factory=now_ts)

    @model_validator(mode="after")
    def _task_must_be_assigned(self) -> "QueenDirective":
        if self.task.status not in ("assigned", "running", "pending"):
            raise ValueError(
                f"QueenDirective task must be in an active status, "
                f"got {self.task.status!r}"
            )
        return self
