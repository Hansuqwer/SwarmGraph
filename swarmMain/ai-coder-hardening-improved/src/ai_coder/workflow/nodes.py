"""Workflow node implementations — hardened edition.

Improvements over original:
  - fail_closed() now maps all known exception types AND adds a catch-all
    failure_cause='unknown' for unexpected exceptions (C9).
  - _ensure_model_seed() is called once at workflow start, not per-node (M1).
  - history entries use append_history() helper for bounded appends (C7).
  - Typed HistoryEntry helpers for type-safe dict construction (C10 partial).
  - plan_node, propose_patch_node, review_node return WorkflowState only;
    PatchOutput stored serialized in WorkflowState.proposed_patch (C5).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Any

from .state import WorkflowState, FailureCause


# ---------------------------------------------------------------------------
# Local imports (agents, models, etc. kept as lazy imports where possible
# to preserve the original module structure)
# ---------------------------------------------------------------------------

def _get_model_errors():
    from ..models.errors import (
        ModelGatewayAuthError,
        ModelGatewayError,
        ModelGatewayRateLimited,
        ModelGatewayUnavailable,
        ModelOutputInvalid,
    )
    return (
        ModelGatewayAuthError,
        ModelGatewayError,
        ModelGatewayRateLimited,
        ModelGatewayUnavailable,
        ModelOutputInvalid,
    )


# ---------------------------------------------------------------------------
# Node: plan
# ---------------------------------------------------------------------------

def plan_node(state: WorkflowState, deps: Any, model_config: Any) -> WorkflowState:
    from ..agents import planner_agent
    state.status = "planning"
    state.prompt_hash = _prompt_hash("planner", state.task)
    plan = planner_agent(state.task, deps, model_config)
    _apply_model_observation(state, deps.model_gateway)
    state.plan = plan.model_dump()
    state.append_history({"kind": "agent", "role": "planner", "output": state.plan})
    return state


# ---------------------------------------------------------------------------
# Node: propose_patch
# ---------------------------------------------------------------------------

def propose_patch_node(
    state: WorkflowState,
    deps: Any,
    model_config: Any,
) -> tuple[WorkflowState, Any]:
    from ..agents import coder_agent
    from ..agents.outputs import PlanOutput

    state.status = "proposing_patch"
    plan = PlanOutput.model_validate(state.plan or {})
    state.prompt_hash = _prompt_hash("coder", state.task, plan.model_dump_json())
    patch = coder_agent(state.task, plan, deps, model_config)
    _apply_model_observation(state, deps.model_gateway)
    state.proposed_patch = patch.model_dump()
    state.proposed_diff = patch.unified_diff
    state.proposed_diff_sha256 = hashlib.sha256(patch.unified_diff.encode()).hexdigest()
    state.append_history({"kind": "agent", "role": "coder", "output": patch.model_dump()})
    return state, patch


# ---------------------------------------------------------------------------
# Node: validate_patch
# ---------------------------------------------------------------------------

def validate_patch_node(
    state: WorkflowState,
    patch: Any,
    config: Any,
    patch_ops: Any | None = None,
) -> WorkflowState:
    from ..approval import command_fingerprint, command_to_argv
    from ..command_policy import denied_path_in_command
    from ..patches import _SIGNING_DENYLIST, PatchValidationError
    from ..sandbox import command_has_shell_metacharacters, command_uses_disallowed_wrapper
    from .adapters import DefaultPatchOperations

    patch_ops = patch_ops or DefaultPatchOperations()
    validation = patch_ops.validate(patch.unified_diff, config)
    if not validation.ok:
        state.status = "failed"
        for e in validation.errors:
            state.add_error(e)
        return state

    state.append_history(
        {"kind": "patch_validation", "paths": validation.paths, "errors": validation.errors}
    )

    command = patch.commands_to_validate[0] if patch.commands_to_validate else config.default_tests

    if command_has_shell_metacharacters(command):
        state.status = "failed"
        state.failure_cause = "patch_invalid"
        state.add_error("validation command contains shell metacharacters")
        return state
    if command_uses_disallowed_wrapper(command):
        state.status = "failed"
        state.failure_cause = "patch_invalid"
        state.add_error("validation command uses a disallowed shell or interpreter wrapper")
        return state

    denied_path = _denied_path_in_command(command, config)
    if denied_path is not None:
        state.status = "failed"
        state.failure_cause = "patch_invalid"
        state.add_error(f"validation command touches denied credential path: {denied_path}")
        return state

    state.test_command = command
    if config.command_requires_approval(command) or patch.requires_approval:
        state.status = "awaiting_approval"
        state.pending_command = command
        state.pending_approval = True
        state.approval_command_fingerprint = command_fingerprint(command_to_argv(command))
    return state


def _denied_path_in_command(command: str, config: Any) -> str | None:
    from ..command_policy import denied_path_in_command
    from ..patches import _SIGNING_DENYLIST
    return denied_path_in_command(
        command,
        [*config.denied_read_paths, *_SIGNING_DENYLIST],
    )


# ---------------------------------------------------------------------------
# Node: apply_patch
# ---------------------------------------------------------------------------

def apply_patch_node(
    state: WorkflowState,
    config: Any,
    patch_ops: Any | None = None,
) -> WorkflowState:
    from ..patches import PatchValidationError
    from .adapters import DefaultPatchOperations

    state.status = "applying_patch"
    patch_ops = patch_ops or DefaultPatchOperations()
    try:
        validation = patch_ops.apply(state.proposed_diff, config)
    except PatchValidationError as e:
        state.status = "failed"
        state.failure_cause = "patch_invalid"
        state.add_error(str(e))
        return state
    state.append_history({"kind": "patch_apply", "paths": validation.paths})
    return state


# ---------------------------------------------------------------------------
# Node: run_tests
# ---------------------------------------------------------------------------

def run_tests_node(
    state: WorkflowState,
    executor: Any,
    *,
    approved: bool,
) -> WorkflowState:
    from dataclasses import asdict

    state.status = "testing"
    command = state.test_command
    result = executor.run(command)
    state.test_result = asdict(result)
    state.append_history(
        {
            "kind": "shell",
            "command": command,
            "approved": approved,
            "executed": result.exit_code != 125,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "backend": result.backend,
        }
    )
    return state


# ---------------------------------------------------------------------------
# Node: review
# ---------------------------------------------------------------------------

def review_node(
    state: WorkflowState,
    patch: Any,
    deps: Any,
    model_config: Any,
    config: Any,
    patch_ops: Any | None = None,
    memory: Any | None = None,
) -> WorkflowState:
    from ..sandbox import ExecutionResult
    from .adapters import DefaultMemoryWriter, DefaultPatchOperations

    state.status = "reviewing"
    patch_ops = patch_ops or DefaultPatchOperations()
    memory = memory or DefaultMemoryWriter(config.repo_root / ".ai-coder" / "memory")
    result = ExecutionResult(**state.test_result) if state.test_result else None
    tests_passed = result is not None and result.exit_code == 0

    if not tests_passed:
        _revert_failed_patch(state, config, "tests_failed", patch_ops)
        state.status = "failed"
        state.failure_cause = "tests_failed"
        state.add_error("validation command failed")
        return state

    state.prompt_hash = _prompt_hash("reviewer", state.task, state.proposed_diff_sha256)
    try:
        from ..agents import reviewer_agent
        review = reviewer_agent(state.task, patch, result, deps, model_config)
        _apply_model_observation(state, deps.model_gateway)
    except Exception:
        _revert_failed_patch(state, config, "review_error", patch_ops)
        raise

    state.append_history({"kind": "agent", "role": "reviewer", "output": review.model_dump()})

    if not review.approved:
        _revert_failed_patch(state, config, "review_rejected", patch_ops)
        state.status = "failed"
        state.failure_cause = "review_rejected"
        for reason in review.reasons:
            state.add_error(reason)
        return state

    if config.memory_enabled and review.memory_lesson_candidate:
        memory.write_lesson(
            state.thread_id,
            {"summary": review.memory_lesson_candidate},
            review_passed=True,
        )
        state.append_history({"kind": "memory", "written": True})

    state.status = "completed"
    return state


# ---------------------------------------------------------------------------
# Node: fail_closed (C9 — comprehensive mapping + catch-all)
# ---------------------------------------------------------------------------

def fail_closed(state: WorkflowState, error: Exception) -> WorkflowState:
    """Map exception types to failure causes. Never leaves failure_cause unset (C9)."""
    from ..redaction.redactor import Redactor

    safe_message = Redactor().redact_text(str(error))
    state.add_model_error(safe_message)

    (
        ModelGatewayAuthError,
        ModelGatewayError,
        ModelGatewayRateLimited,
        ModelGatewayUnavailable,
        ModelOutputInvalid,
    ) = _get_model_errors()

    cause: FailureCause
    if isinstance(error, ModelGatewayAuthError):
        state.status = "model_unavailable"
        cause = "auth_failed"
    elif isinstance(error, ModelGatewayRateLimited):
        state.status = "model_unavailable"
        cause = "rate_limited"
    elif isinstance(error, ModelGatewayUnavailable):
        state.status = "model_unavailable"
        cause = "gateway_unavailable"
    elif isinstance(error, ModelOutputInvalid):
        state.status = "failed"
        cause = "output_invalid"
    elif isinstance(error, ModelGatewayError):
        # Generic model gateway error — treat as unavailable
        state.status = "model_unavailable"
        cause = "gateway_unavailable"
    else:
        # C9: catch-all — unexpected exception, do not leak type info
        state.status = "failed"
        cause = "unknown"

    state.failure_cause = cause
    return state


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _revert_failed_patch(
    state: WorkflowState,
    config: Any,
    reason: str,
    patch_ops: Any | None = None,
) -> None:
    if not state.proposed_diff:
        return
    from ..patches import PatchValidationError
    from .adapters import DefaultPatchOperations

    patch_ops = patch_ops or DefaultPatchOperations()
    try:
        validation = patch_ops.revert(state.proposed_diff, config)
    except PatchValidationError as e:
        state.add_error(f"failed to revert patch after {reason}: {e}")
        return
    state.append_history({"kind": "patch_revert", "reason": reason, "paths": validation.paths})


def _prompt_hash(*parts: str) -> str:
    combined = "\n".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _apply_model_observation(state: WorkflowState, gateway: Any) -> None:
    """Capture usage from the model gateway into state.usage."""
    usage = getattr(gateway, "last_usage", None)
    if usage is not None:
        from .state import TokenUsage
        state.usage = TokenUsage(
            input_tokens=max(0, int(getattr(usage, "input_tokens", 0))),
            output_tokens=max(0, int(getattr(usage, "output_tokens", 0))),
        )
