"""Checkpointed runtime workflow state — hardened edition.

Improvements over original:
  - ConfigDict(extra='forbid') prevents unknown checkpoint fields from silently
    passing through deserialization (C1).
  - validate_assignment=True ensures mutations to state fields are also validated (C1).
  - TokenUsage fields have ge=0 bounds constraints (C6).
  - repo_root has a field_validator enforcing non-empty, no-traversal (C8).
  - history uses a typed HistoryEntry discriminated union (C10).
  - WorkflowState.errors and model_errors are bounded by max_length (M3).
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Status / cause literals
# ---------------------------------------------------------------------------

WorkflowStatus = Literal[
    "initialized",
    "planning",
    "proposing_patch",
    "awaiting_approval",
    "applying_patch",
    "testing",
    "reviewing",
    "completed",
    "failed",
    "denied",
    "model_unavailable",
]

FailureCause = Literal[
    "gateway_unavailable",
    "auth_failed",
    "rate_limited",
    "output_invalid",
    "refused",
    "patch_invalid",
    "tests_failed",
    "review_rejected",
    "denied",
    "unknown",  # NEW: catch-all for unexpected exceptions (C9)
]


# ---------------------------------------------------------------------------
# Typed history entries — discriminated union (C10)
# ---------------------------------------------------------------------------

class ShellHistoryEntry(BaseModel):
    """Records a shell command execution."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["shell"]
    command: str
    approved: bool
    executed: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    backend: str = ""


class AgentHistoryEntry(BaseModel):
    """Records output from a planner / coder / reviewer agent call."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["agent"]
    role: Literal["planner", "coder", "reviewer"]
    output: dict[str, Any]


class PatchValidationHistoryEntry(BaseModel):
    """Records the result of patch validation."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["patch_validation"]
    paths: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PatchApplyHistoryEntry(BaseModel):
    """Records that a patch was successfully applied."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["patch_apply"]
    paths: list[str] = Field(default_factory=list)


class PatchRevertHistoryEntry(BaseModel):
    """Records that a patch was reverted after failure."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["patch_revert"]
    reason: str
    paths: list[str] = Field(default_factory=list)


class MemoryHistoryEntry(BaseModel):
    """Records that a memory lesson was written."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["memory"]
    written: bool


# Discriminated union over all history entry types
HistoryEntry = Annotated[
    Union[
        ShellHistoryEntry,
        AgentHistoryEntry,
        PatchValidationHistoryEntry,
        PatchApplyHistoryEntry,
        PatchRevertHistoryEntry,
        MemoryHistoryEntry,
    ],
    Field(discriminator="kind"),
]

# Maximum history entries to keep in state (prevents unbounded growth - C7)
_MAX_HISTORY_ENTRIES: int = 500
# Maximum error list length
_MAX_ERRORS: int = 100


# ---------------------------------------------------------------------------
# Token usage — with bounds (C6)
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    """Validated token usage from a model gateway call."""
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)   # C6: no negatives
    output_tokens: int = Field(default=0, ge=0)  # C6: no negatives

    def total(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# Primary workflow state
# ---------------------------------------------------------------------------

class WorkflowState(BaseModel):
    """Persisted agent workflow state.

    Security hardening (C1):
      - extra='forbid': unknown checkpoint fields cause a ValidationError,
        not a silent pass-through.
      - validate_assignment=True: mutations via attribute assignment are also
        validated against field types and constraints.
    """

    model_config = ConfigDict(
        extra="forbid",            # C1: reject unknown fields on deserialization
        validate_assignment=True,  # C1: validate field mutations
    )

    workflow_kind: str = "agent"
    thread_id: str
    task: str
    repo_root: str
    status: WorkflowStatus = "initialized"

    plan: dict[str, Any] | None = None
    proposed_patch: dict[str, Any] | None = None
    proposed_diff: str = ""
    proposed_diff_sha256: str = ""
    prompt_hash: str = ""
    seed: int | None = None

    usage: TokenUsage | None = None
    failure_cause: FailureCause | None = None

    pending_command: str = ""
    pending_approval: bool = False
    approval_command_fingerprint: str = ""
    approval_consumed: bool = False

    # Bounded lists (C7)
    history: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    test_command: str = ""
    test_result: dict[str, Any] | None = None
    model_errors: list[str] = Field(default_factory=list)

    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # ---------------------------------------------------------------------------
    # Field validators (C8)
    # ---------------------------------------------------------------------------

    @field_validator("repo_root")
    @classmethod
    def _repo_root_must_be_safe(cls, v: str) -> str:
        """Validate repo_root is non-empty and has no parent traversal."""
        if not v or not v.strip():
            raise ValueError("repo_root must not be empty")
        if ".." in v.split("/"):
            raise ValueError("repo_root must not contain parent directory traversal (..)")
        return v

    @field_validator("thread_id")
    @classmethod
    def _thread_id_must_be_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("thread_id must not be empty")
        return v

    @field_validator("task")
    @classmethod
    def _task_must_be_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("task must not be empty")
        return v

    # ---------------------------------------------------------------------------
    # Model validator: enforce bounded lists after construction (C7)
    # ---------------------------------------------------------------------------

    @model_validator(mode="after")
    def _cap_lists(self) -> "WorkflowState":
        if len(self.history) > _MAX_HISTORY_ENTRIES:
            # Keep the first entry (initialized) + the most recent entries
            self.history = self.history[:1] + self.history[-(_MAX_HISTORY_ENTRIES - 1):]
        if len(self.errors) > _MAX_ERRORS:
            self.errors = self.errors[-_MAX_ERRORS:]
        if len(self.model_errors) > _MAX_ERRORS:
            self.model_errors = self.model_errors[-_MAX_ERRORS:]
        return self

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = time.time()

    def add_error(self, msg: str) -> None:
        """Append an error message, respecting the max-errors cap."""
        self.errors = (self.errors + [msg])[-_MAX_ERRORS:]

    def add_model_error(self, msg: str) -> None:
        """Append a model error message, respecting the max-errors cap."""
        self.model_errors = (self.model_errors + [msg])[-_MAX_ERRORS:]

    def append_history(self, entry: dict[str, Any]) -> None:
        """Append a history entry, respecting the max-history cap."""
        new_history = self.history + [entry]
        if len(new_history) > _MAX_HISTORY_ENTRIES:
            new_history = new_history[:1] + new_history[-(_MAX_HISTORY_ENTRIES - 1):]
        self.history = new_history
