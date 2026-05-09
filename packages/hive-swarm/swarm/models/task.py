"""Task models — patched.

F-08A: real no-self-dependency check (the previous _no_self_dep only deduplicated)
F-08B: task.fail("") rejected
F-08-T1: refresh result_hash on every revalidation
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel, HardenedModel, now_ts, stable_hash
from .types import AgentRole, TaskPriority, TaskStatus


class SwarmTask(HardenedModel):
    """One atomic unit of work."""

    task_id: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=4096)
    priority: TaskPriority = "medium"
    status: TaskStatus = "pending"
    assigned_to: str | None = None
    required_role: AgentRole | None = None

    depends_on: list[str] = Field(default_factory=list, max_length=64)

    result_summary: str = ""
    result_hash: str = ""

    context: dict[str, Any] = Field(default_factory=dict, max_length=64)
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
    def _dedupe_deps(cls, v: list[str]) -> list[str]:
        """Deduplicate while preserving order."""
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _no_self_dependency(self) -> SwarmTask:
        # F-08A: real self-dep check (was missing)
        if self.task_id in self.depends_on:
            raise ValueError(f"task {self.task_id!r} cannot depend on itself")
        return self

    @model_validator(mode="after")
    def _refresh_result_hash(self) -> SwarmTask:
        # F-08-T1: always recompute when result_summary present
        if self.result_summary:
            object.__setattr__(self, "result_hash", stable_hash(self.result_summary))
        else:
            object.__setattr__(self, "result_hash", "")
        return self

    # ── Lifecycle helpers ──────────────────────────────────────────────────

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

    def fail(self, reason: str) -> None:
        # F-08B: reject empty reason
        if not reason or not reason.strip():
            raise ValueError("fail() requires a non-empty reason")
        self.status = "failed"
        self.result_summary = reason
        self.completed_at = now_ts()

    def cancel(self) -> None:
        self.status = "cancelled"
        self.completed_at = now_ts()

    def is_ready(self, completed_task_ids: set[str]) -> bool:
        return all(dep in completed_task_ids for dep in self.depends_on)

    def priority_value(self) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[self.priority]


class QueenDirective(FrozenModel):
    """Immutable instruction from queen to one worker."""

    directive_id: str = Field(..., min_length=1)
    task: SwarmTask
    assigned_agent_id: str = Field(..., min_length=1)
    assigned_role: AgentRole
    objective_hash: str = Field(..., min_length=1)
    shared_context: dict[str, Any] = Field(default_factory=dict, max_length=32)
    issued_at: float = Field(default_factory=now_ts)

    @model_validator(mode="after")
    def _task_must_be_assigned(self) -> QueenDirective:
        if self.task.status not in ("assigned", "running", "pending"):
            raise ValueError(
                f"QueenDirective task must be in an active status, got {self.task.status!r}"
            )
        return self


__all__ = ["SwarmTask", "QueenDirective"]
